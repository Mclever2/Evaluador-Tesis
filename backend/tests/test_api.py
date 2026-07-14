"""Tests de la API FastAPI: subida, evaluación en segundo plano con panel
doble, exportación y chat. Sin llamadas a OpenAI y con data/ en tmp_path."""

from __future__ import annotations

import time

import fitz
import pytest
from fastapi.testclient import TestClient

from app import runner, storage
from app.chat import RespuestaChat
from app.main import app
from graph.evaluation_graph import PanelEvaluador
from graph.llm import UsoLLM
from tests.test_graph import _fake_invocador
from tests.test_segmenter import _doc_sintetico


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "ecm.sqlite3")
    monkeypatch.setattr(storage, "results_dir", lambda: tmp_path / "results")

    def panel_doble(on_evento):
        return PanelEvaluador(
            invocadores={n: _fake_invocador() for n in (1, 2, 3)},
            modelos={n: f"doble-{n}" for n in (1, 2, 3)},
            on_evento=on_evento,
        )

    monkeypatch.setattr(runner, "crear_panel", panel_doble)
    with TestClient(app) as tc:
        yield tc


def _pdf_sintetico() -> bytes:
    doc = fitz.open()
    for pagina_texto in _doc_sintetico().paginas:
        pagina = doc.new_page()
        pagina.insert_textbox(fitz.Rect(40, 40, 555, 800), pagina_texto.texto, fontsize=9)
    return doc.tobytes()


def _subir(cliente) -> str:
    respuesta = cliente.post(
        "/projects/upload",
        files={"archivo": ("proyecto.pdf", _pdf_sintetico(), "application/pdf")},
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["project_id"]


def _evaluar_y_esperar(cliente, project_id: str, cuerpo: dict | None = None) -> dict:
    respuesta = cliente.post(f"/projects/{project_id}/evaluate", json=cuerpo or {})
    assert respuesta.status_code == 200, respuesta.text
    evaluation_id = respuesta.json()["evaluation_id"]
    for _ in range(600):  # 30s: la primera importación de pandas/pingouin es lenta
        registro_eval = cliente.get(f"/evaluations/{evaluation_id}").json()
        if registro_eval["estado"] in ("completada", "error"):
            return registro_eval
        time.sleep(0.05)
    pytest.fail("la evaluación no terminó a tiempo")


class TestFlujoCompleto:
    def test_subida_produce_reporte_de_indexacion(self, cliente):
        respuesta = cliente.post(
            "/projects/upload",
            files={"archivo": ("proyecto.pdf", _pdf_sintetico(), "application/pdf")},
        )
        assert respuesta.status_code == 200
        datos = respuesta.json()
        assert datos["estado"] == "indexado"
        reporte = datos["reporte_indexacion"]
        assert len(reporte["secciones"]) == 15
        presentes = [s for s in reporte["secciones"] if s["presente"]]
        assert len(presentes) == 13
        assert reporte["anonimizacion"] is not None
        # El mapeo de anonimización NO viaja en la respuesta
        assert "mapeo" not in datos and "mapeo" not in reporte

    def test_index_report_persistido(self, cliente):
        project_id = _subir(cliente)
        reporte = cliente.get(f"/projects/{project_id}/index-report").json()
        assert len(reporte["no_encontradas"]) == 2

    def test_evaluacion_completa(self, cliente):
        project_id = _subir(cliente)
        registro_eval = _evaluar_y_esperar(cliente, project_id)
        assert registro_eval["estado"] == "completada"
        resultado = registro_eval["resultado"]
        assert resultado["total"] == 92
        assert resultado["nivel"] == "Excelente"
        assert resultado["metricas_deterministicas"]["completitud"]["presentes"] == 13

    def test_evaluacion_progresiva(self, cliente):
        project_id = _subir(cliente)
        registro_eval = _evaluar_y_esperar(
            cliente, project_id, {"mode": "progresivo", "semanas_activas": [3]}
        )
        resultado = registro_eval["resultado"]
        assert resultado["total"] == 7
        assert resultado["total_normalizado"] == 70.0

    def test_export_json_y_csv(self, cliente):
        project_id = _subir(cliente)
        registro_eval = _evaluar_y_esperar(cliente, project_id)
        evaluation_id = registro_eval["id"]

        json_resp = cliente.get(f"/evaluations/{evaluation_id}/export?format=json")
        assert json_resp.status_code == 200
        assert json_resp.json()["total"] == 92

        csv_resp = cliente.get(f"/evaluations/{evaluation_id}/export?format=csv")
        assert csv_resp.status_code == 200
        lineas = csv_resp.text.strip().splitlines()
        assert lineas[0].startswith("project_id,rubric_id")
        assert len(lineas) == 1 + 85  # cabecera + un ítem por fila

    def test_consolidado_una_fila_por_proyecto(self, cliente):
        p1 = _subir(cliente)
        p2 = _subir(cliente)
        _evaluar_y_esperar(cliente, p1)
        _evaluar_y_esperar(cliente, p2)
        respuesta = cliente.get("/evaluations/export/consolidated.csv")
        assert respuesta.status_code == 200
        lineas = respuesta.text.strip().splitlines()
        assert len(lineas) == 3  # cabecera + 2 proyectos
        cabecera = lineas[0].split(",")
        for columna in ("total", "nivel", "sub_S01", "sub_S15",
                        "trans_coherencia_interna", "fernandez_huerta",
                        "pct_discrepancia", "panel_incompleto"):
            assert columna in cabecera, columna

    def test_chat_sobre_el_informe(self, cliente, monkeypatch):
        from app import chat as chat_mod

        def invocador_doble():
            def invocar(prompt, schema):
                assert schema is RespuestaChat
                assert "solo evalúa" in prompt or "informe" in prompt.lower()
                return RespuestaChat(respuesta="El ítem 1.1 salió cumple."), UsoLLM()

            return invocar

        monkeypatch.setattr(chat_mod, "invocador_por_defecto", invocador_doble)
        project_id = _subir(cliente)
        registro_eval = _evaluar_y_esperar(cliente, project_id)
        respuesta = cliente.post(
            f"/evaluations/{registro_eval['id']}/chat",
            json={"pregunta": "¿Por qué el ítem 1.1 salió cumple?"},
        )
        assert respuesta.status_code == 200
        assert "1.1" in respuesta.json()["respuesta"]

    def test_rubricas_y_salud(self, cliente):
        rubricas = cliente.get("/rubrics").json()
        assert any(r["id"] == "especifica_v1" for r in rubricas)
        assert cliente.get("/health").json()["estado"] == "ok"

    def test_formato_no_soportado(self, cliente):
        respuesta = cliente.post(
            "/projects/upload", files={"archivo": ("x.txt", b"hola", "text/plain")}
        )
        assert respuesta.status_code == 400


class TestClaveDeAcceso:
    def test_exige_clave_cuando_esta_configurada(self, cliente, monkeypatch):
        from app import auth, main as main_mod
        from app.config import Settings

        ajustes = Settings(app_access_key="secreta")
        monkeypatch.setattr(main_mod, "get_settings", lambda: ajustes)
        monkeypatch.setattr(auth, "get_settings", lambda: ajustes)
        assert cliente.get("/health").status_code == 401
        assert cliente.get("/health", headers={"X-Access-Key": "secreta"}).status_code == 200


class TestAccesoSupabase:
    def test_exige_bearer_de_supabase(self, cliente, monkeypatch):
        from app import auth

        ajustes_supabase = type(
            "S", (), {"supabase_url": "https://x.supabase.co",
                      "supabase_anon_key": "anon", "app_access_key": None}
        )()
        monkeypatch.setattr(auth, "get_settings", lambda: ajustes_supabase)
        monkeypatch.setattr(auth, "_validar_contra_supabase", lambda token: token == "bueno")
        monkeypatch.setattr(auth, "_cache_tokens", {})

        assert cliente.get("/health").status_code == 401
        assert cliente.get(
            "/health", headers={"Authorization": "Bearer malo"}
        ).status_code == 401
        assert cliente.get(
            "/health", headers={"Authorization": "Bearer bueno"}
        ).status_code == 200
        # La segunda petición con el mismo token usa el caché
        monkeypatch.setattr(auth, "_validar_contra_supabase", lambda token: False)
        assert cliente.get(
            "/health", headers={"Authorization": "Bearer bueno"}
        ).status_code == 200
