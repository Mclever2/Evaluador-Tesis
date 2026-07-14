"""Tests del CLI batch (carpeta → CSV consolidado) y del test-retest, con
panel doble determinista. Sin llamadas a OpenAI."""

from __future__ import annotations

import csv
from pathlib import Path

import fitz
import pytest

from app import runner, storage
from cli.batch_eval import main as batch_main
from cli.retest import ejecutar_retest, escribir_reporte
from graph.evaluation_graph import PanelEvaluador
from tests.test_graph import _fake_invocador
from tests.test_segmenter import _doc_sintetico


@pytest.fixture()
def entorno(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(storage, "PROJECTS_DIR", tmp_path / "data" / "projects")
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "data" / "ecm.sqlite3")
    monkeypatch.setattr(storage, "results_dir", lambda: tmp_path / "data" / "results")

    def panel_doble(_on_evento):
        return PanelEvaluador(
            invocadores={n: _fake_invocador() for n in (1, 2, 3)},
            modelos={n: f"doble-{n}" for n in (1, 2, 3)},
        )

    monkeypatch.setattr(runner, "crear_panel", panel_doble)

    carpeta = tmp_path / "proyectos"
    carpeta.mkdir()
    for nombre in ("tesis_a", "tesis_b"):
        pdf = fitz.open()
        for pagina_texto in _doc_sintetico().paginas:
            pagina = pdf.new_page()
            pagina.insert_textbox(fitz.Rect(40, 40, 555, 800), pagina_texto.texto, fontsize=9)
        pdf.save(carpeta / f"{nombre}.pdf")
    return carpeta, tmp_path


class TestBatch:
    def test_carpeta_produce_csv_consolidado(self, entorno):
        carpeta, tmp_path = entorno
        salida = tmp_path / "consolidado.csv"
        codigo = batch_main([str(carpeta), "--salida", str(salida)])
        assert codigo == 0
        with salida.open(encoding="utf-8") as archivo:
            filas = list(csv.DictReader(archivo))
        assert len(filas) == 2  # una fila por proyecto
        assert {f["project_id"] for f in filas} == {"tesis_a", "tesis_b"}
        assert filas[0]["total"] == "92.0"
        assert filas[0]["sub_S01"] == "5.0"
        assert filas[0]["sub_S15"] == "3.0"
        assert "trans_coherencia_interna" in filas[0]
        assert "pct_discrepancia" in filas[0]

    def test_batch_persiste_en_storage(self, entorno):
        carpeta, tmp_path = entorno
        batch_main([str(carpeta), "--salida", str(tmp_path / "c.csv")])
        completadas = storage.evaluaciones_completadas()
        assert len(completadas) == 2
        assert all(r["resultado"]["total"] == 92 for r in completadas)


class TestRetest:
    def test_k_corridas_identicas_dan_qwk_1(self, entorno):
        carpeta, tmp_path = entorno
        resumen = ejecutar_retest(carpeta, k=3, rubrica="especifica_v1")
        assert resumen["k"] == 3
        assert set(resumen["qwk_pares"]) == {
            "corrida1|corrida2", "corrida1|corrida3", "corrida2|corrida3"
        }
        # Panel doble determinista → corridas idénticas
        assert resumen["qwk_promedio"] == pytest.approx(1.0)
        assert resumen["identicos_promedio"] == pytest.approx(1.0)

        ruta = escribir_reporte(resumen, tmp_path / "validation", "especifica_v1")
        contenido = ruta.read_text(encoding="utf-8")
        assert "test-retest" in contenido.lower()
        assert (tmp_path / "validation" / "retest_totales.csv").exists()
