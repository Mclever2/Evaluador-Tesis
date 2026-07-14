"""Test de integración del grafo completo con jueces dobles (sin API de OpenAI)."""

from __future__ import annotations

import re

import pytest

from graph.evaluation_graph import ConfigEvaluacion, PanelEvaluador, secciones_activas_para
from graph.llm import UsoLLM
from graph.schemas import (
    CalificacionDimension,
    CalificacionItemPonderado,
    DIMENSIONES_TRANSVERSALES,
    RespuestaSeccionPonderada,
    RespuestaTransversales,
)
from rubrics import load_rubric
from tests.test_segmenter import _doc_sintetico


def _fake_invocador(nivel_por_item=None, default="cumple"):
    """Doble del invocador: extrae los ids de ítems del propio prompt renderizado."""
    niveles = nivel_por_item or {}

    def invocador(prompt: str, schema):
        if schema is RespuestaSeccionPonderada:
            ids = re.findall(r"^- \[([\d.]+)\]", prompt, re.MULTILINE)
            assert ids, "el prompt del juez debe listar los criterios como '- [id]'"
            assert "no reescribas" in prompt.lower()
            return (
                RespuestaSeccionPonderada(
                    calificaciones=[
                        CalificacionItemPonderado(
                            item_id=i,
                            deficiencias="ninguna",
                            nivel=niveles.get(i, default),
                            evidencia="«cita textual» (sección)",
                            observacion="diagnóstico breve",
                        )
                        for i in ids
                    ]
                ),
                UsoLLM(tokens_entrada=100, tokens_salida=40),
            )
        if schema is RespuestaTransversales:
            return (
                RespuestaTransversales(
                    dimensiones=[
                        CalificacionDimension(dimension=d, puntaje=4, justificacion="adecuado")
                        for d in DIMENSIONES_TRANSVERSALES
                    ]
                ),
                UsoLLM(tokens_entrada=200, tokens_salida=30),
            )
        raise AssertionError(f"schema inesperado en el doble: {schema}")

    return invocador


def _panel(por_juez: dict | None = None):
    por_juez = por_juez or {}
    eventos = []
    panel = PanelEvaluador(
        invocadores={
            1: por_juez.get(1, _fake_invocador()),
            2: por_juez.get(2, _fake_invocador()),
            3: por_juez.get(3, _fake_invocador()),
        },
        modelos={1: "doble-1", 2: "doble-2", 3: "doble-3"},
        on_evento=eventos.append,
    )
    return panel, eventos


class TestGrafoCompleto:
    def test_evaluacion_completa_sintetica(self):
        panel, eventos = _panel()
        resultado = panel.evaluar(
            _doc_sintetico(), None, ConfigEvaluacion(project_id="p1")
        )
        # 13/15 secciones presentes, todo cumple → 100 - S06(3) - S10(5) = 92
        assert resultado.total == 92
        assert resultado.nivel == "Excelente"
        assert resultado.puntaje_max_activo == 100
        assert resultado.total_normalizado is None
        ausentes = [s for s in resultado.secciones if not s.presente]
        assert {s.id for s in ausentes} == {"S06", "S10"}
        assert all(s.subtotal == 0 for s in ausentes)
        assert resultado.panel.pct_discrepancia == 0
        assert resultado.panel.panel_incompleto is False
        assert [d.mediana for d in resultado.dimensiones_transversales] == [4, 4, 4]
        # 3 jueces × (13 secciones + 1 transversal) = 42 llamadas de 100/40 y 200/30
        assert resultado.costo.tokens_entrada == 3 * (13 * 100 + 200)
        assert resultado.costo.usd_estimado is None  # modelos dobles sin precio
        assert resultado.config_modelos == {"juez1": "doble-1", "juez2": "doble-2", "juez3": "doble-3"}
        assert len(resultado.prompts_hash) == 16
        assert resultado.reporte_indexacion["secciones"][0]["id"] == "S01"
        assert any(e["tipo"] == "resultado" for e in eventos)
        # Las métricas determinísticas acompañan cada evaluación
        metricas = resultado.metricas_deterministicas
        assert metricas is not None
        assert metricas["completitud"]["presentes"] == 13
        assert metricas["palabras_totales"] > 0

    def test_discrepancia_marcada_en_grafo(self):
        panel, _ = _panel({3: _fake_invocador(nivel_por_item={"1.1": "no_cumple"})})
        resultado = panel.evaluar(_doc_sintetico(), None, ConfigEvaluacion(project_id="p2"))
        assert "S01.1.1" in resultado.panel.items_marcados
        item = next(i for i in resultado.secciones[0].items if i.id == "1.1")
        assert item.nivel_final == "cumple"  # mediana de (cumple, cumple, no_cumple)
        assert item.discrepancia is True
        assert resultado.total == 92  # la mediana no cambió el puntaje

    def test_modo_progresivo_por_semanas(self):
        panel, _ = _panel()
        resultado = panel.evaluar(
            _doc_sintetico(),
            None,
            ConfigEvaluacion(project_id="p3", mode="progresivo", semanas_activas=[3]),
        )
        # Semana 3 → S05 y S06; S06 ausente → total 7 de 10 → 70 normalizado
        assert resultado.puntaje_max_activo == 10
        assert resultado.total == 7
        assert resultado.total_normalizado == 70.0
        assert resultado.nivel == "Regular"
        activas = [s for s in resultado.secciones if s.activa]
        assert {s.id for s in activas} == {"S05", "S06"}

    def test_semanas_activas_union(self):
        rubrica = load_rubric("especifica_v1")
        config = ConfigEvaluacion(
            project_id="x", mode="progresivo", semanas_activas=[1, 2]
        )
        assert secciones_activas_para(rubrica, config) == {"S01", "S02", "S03", "S04"}

    def test_ficha_sin_administrativos_excluye_b06(self):
        rubrica = load_rubric("ficha_upao_v1")
        config = ConfigEvaluacion(
            project_id="x", rubric_id="ficha_upao_v1", incluir_administrativos=False
        )
        assert secciones_activas_para(rubrica, config) == {
            "B01", "B02", "B03", "B04", "B05", "B07"
        }

    def test_seccion_vacia_no_gasta_llamadas(self):
        from graph.judges import construir_configuracion_panel, evaluar_con_juez
        from graph.segmenter import segmentar

        doc = _doc_sintetico()
        rubrica = load_rubric("especifica_v1")
        segmentacion = segmentar(doc, rubrica)
        s15 = next(s for s in segmentacion.secciones if s.seccion_id == "S15")
        s15.texto = "SPSS."
        s15.palabras = 1  # sin contenido evaluable

        secciones_llamadas: list[str] = []
        base = _fake_invocador()

        def espia(prompt, schema):
            import re as _re

            m = _re.search(r'Evalúa la sección "([^"]+)"', prompt)
            if m:
                secciones_llamadas.append(m.group(1))
            return base(prompt, schema)

        cfg = construir_configuracion_panel({1: "doble"})[0]
        activas = {s.id for s in rubrica.secciones}
        evaluar_con_juez(cfg, espia, rubrica, segmentacion, activas)
        assert all("procesamiento" not in s.lower() for s in secciones_llamadas)
        assert len(secciones_llamadas) == 12  # 13 presentes - 1 vacía

    def test_hueco_persistente_marca_panel_incompleto(self):
        base = _fake_invocador()

        def juez_fallando(prompt, schema):
            if schema is RespuestaSeccionPonderada and "Título" in prompt:
                raise TimeoutError("API caída simulada")
            return base(prompt, schema)

        panel, _ = _panel({2: juez_fallando})
        resultado = panel.evaluar(_doc_sintetico(), None, ConfigEvaluacion(project_id="p4"))
        assert resultado.panel.panel_incompleto is True
        assert any("S01" in h for h in resultado.panel.huecos)
        # Los demás jueces sostienen la sección: S01 sigue puntuando
        assert resultado.secciones[0].subtotal == 5
