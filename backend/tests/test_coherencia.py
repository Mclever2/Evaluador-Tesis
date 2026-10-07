"""Análisis de coherencia externos a la rúbrica: índice argumentativo (Toulmin) y coherencia global.

Se prueban las reglas fijas (elegibilidad, segmentación, calificadores, puntaje, verificación de citas y
nota) y la integración con el grafo mediante dobles del invocador (sin API de OpenAI).
"""

from __future__ import annotations

import re

from graph.analisis_texto import cita_en_texto, elegibilidad, palabras
from graph.argumentacion import calificadores_en, oraciones, puntuar
from graph.coherencia_global import nota_por_regla, verificar
from graph.evaluation_graph import ConfigEvaluacion, PanelEvaluador
from graph.llm import UsoLLM
from graph.schemas import (
    Contradiccion,
    EtiquetaOracion,
    RespuestaArgumentacion,
    RespuestaCoherencia,
)
from tests.test_graph import _fake_invocador
from tests.test_segmenter import _doc_sintetico

PROSA = ("La empresa registra retrasos en el 23 % de sus pedidos según el reporte anual de 2024. "
         "Esta situación genera pérdidas económicas y reclamos de los clientes en la región. "
         "Lo cual indica que el control actual del inventario es insuficiente para la demanda. ") * 3


class TestElegibilidad:
    def test_prosa_completa_es_elegible(self):
        e = elegibilidad(PROSA)
        assert e["elegible"] and e["proporcion_oraciones"] > 0.9

    def test_apuntes_no_son_elegibles(self):
        apuntes = "\n".join(["Comparar con desarrolladores", "consumo de créditos", "ver alucinación"] * 10)
        assert not elegibilidad(apuntes)["elegible"]

    def test_viñetas_con_oraciones_completas_son_elegibles(self):
        texto = "\n".join("● Justificación teórica: " + o for o in [PROSA] * 2)
        assert elegibilidad(texto)["elegible"]


class TestSegmentacion:
    def test_une_lineas_partidas_y_separa_rotulos(self):
        texto = ("Contexto local y delimitación del problema:\n"
                 "En las entidades públicas el análisis manual de los\n"
                 "términos de referencia presenta limitaciones estructurales.\n"
                 "Frente a ello se requiere un sistema automatizado de validación.")
        ors = oraciones(texto)
        assert ors[0] == "Contexto local y delimitación del problema:"
        assert ors[1].startswith("En las entidades públicas") and ors[1].endswith("estructurales.")
        assert len(ors) == 3

    def test_respeta_et_al(self):
        ors = oraciones("Según Pérez et al. (2020) el retraso es alto en la región norte del país. "
                        "Otros estudios confirman la tendencia observada.")
        assert len(ors) == 2


class TestCalificadoresYPuntaje:
    def test_diccionario_de_atenuadores(self):
        assert calificadores_en("Los métodos suelen fallar y resuelven el problema solo en parte.") == \
            ["suelen", "solo en parte"]
        assert calificadores_en("El sistema puede procesar datos.") == []
        assert calificadores_en("Se justifica prácticamente porque resuelve un problema.") == []
        assert calificadores_en("La investigación es prácticamente nula.") == ["prácticamente nula"]

    def test_nivel_e_indice(self):
        ors = ["Existe un problema de retrasos en la empresa estudiada.",
               "El 23 % de los pedidos se retrasa según el reporte anual.",
               "Podría argumentarse que los retrasos dependen de la temporada.",
               "Sin embargo, los retrasos persisten en todos los meses del año."]
        etiquetas = [EtiquetaOracion(id=1, funcion="afirmacion"), EtiquetaOracion(id=2, funcion="dato"),
                     EtiquetaOracion(id=3, funcion="refutacion", responde_en=4),
                     EtiquetaOracion(id=4, funcion="dato")]
        p = puntuar(etiquetas, ors)
        assert p["nivel"] == 4  # una refutación respondida
        assert p["presentes"] == ["afirmacion", "dato", "refutacion"]
        assert p["indice_estructural"] == 0.5

    def test_sin_afirmacion_es_nivel_cero(self):
        p = puntuar([EtiquetaOracion(id=1, funcion="dato")], ["Un dato cualquiera del estudio citado."])
        assert p["nivel"] == 0


class TestCoherenciaGlobal:
    TEXTO = ("¿En qué medida el prototipo mejora la precisión del análisis estructural de muros? "
             "Evaluar el efecto del prototipo en la exactitud numérica del análisis estructural de muros.")

    def test_cita_tolera_cortes_de_pdf_y_rechaza_inventadas(self):
        texto = palabras("el prototipo mejora la preci-\nsión del análisis estructural de muros")
        assert cita_en_texto("el prototipo mejora la precisión del análisis estructural", texto)
        assert not cita_en_texto("el sistema reduce los costos operativos de la empresa", texto)

    def test_verifica_y_clasifica_gravedad(self):
        respuesta = RespuestaCoherencia(contradicciones=[
            Contradiccion(tipo="variables", seccion_a="Formulación", seccion_b="Objetivos",
                          cita_a="el prototipo mejora la precisión del análisis estructural",
                          cita_b="el prototipo en la exactitud numérica del análisis estructural",
                          explicacion="precisión y exactitud son conceptos distintos"),
            Contradiccion(tipo="muestreo", seccion_a="Población", seccion_b="Objetivos",
                          cita_a="cita inventada que no existe en el proyecto evaluado",
                          cita_b="el prototipo en la exactitud numérica del análisis estructural",
                          explicacion="no verificable"),
        ])
        verificadas, rechazadas = verificar(respuesta, self.TEXTO)
        assert len(verificadas) == 1 and verificadas[0].gravedad == "nucleo"
        assert rechazadas[0]["motivo_rechazo"] == "cita no encontrada en el texto"

    def test_nota_por_regla(self):
        assert nota_por_regla(0, 0) == 5
        assert nota_por_regla(0, 1) == 4
        assert nota_por_regla(1, 0) == 3
        assert nota_por_regla(0, 2) == 3
        assert nota_por_regla(1, 2) == 2
        assert nota_por_regla(3, 0) == 1


def _fake_analisis(prompt: str, schema):
    """Doble del invocador de análisis: etiqueta todo como afirmación y no encuentra contradicciones."""
    if schema is RespuestaArgumentacion:
        n = int(re.search(r"del 1 al (\d+)", prompt).group(1))
        return (RespuestaArgumentacion(etiquetas=[EtiquetaOracion(id=i, funcion="afirmacion")
                                                  for i in range(1, n + 1)]),
                UsoLLM(tokens_entrada=50, tokens_salida=10))
    if schema is RespuestaCoherencia:
        assert "¿pueden ser verdad AMBAS citas a la vez" in prompt
        return RespuestaCoherencia(contradicciones=[]), UsoLLM(tokens_entrada=80, tokens_salida=5)
    raise AssertionError(f"schema inesperado: {schema}")


class TestIntegracionGrafo:
    def test_resultado_incluye_ambos_analisis_sin_tocar_la_rubrica(self):
        panel = PanelEvaluador(invocadores={n: _fake_invocador() for n in (1, 2, 3)},
                               modelos={1: "doble-1", 2: "doble-2", 3: "doble-3"},
                               invocador_analisis=_fake_analisis, modelo_analisis="doble-analisis")
        resultado = panel.evaluar(_doc_sintetico(), None, ConfigEvaluacion(project_id="p-coh"))
        assert resultado.total == 92  # la rúbrica no cambia
        assert resultado.coherencia_global is not None and resultado.coherencia_global.nota == 5
        assert resultado.argumentacion is not None
        assert resultado.argumentacion.version == "1.1" and resultado.coherencia_global.version == "1.3"
        assert {s.seccion_id for s in resultado.argumentacion.secciones} == {"S02", "S05"}

    def test_fallo_del_analisis_no_invalida_la_rubrica(self):
        def falla(prompt, schema):
            raise TimeoutError("API caída simulada")

        panel = PanelEvaluador(invocadores={n: _fake_invocador() for n in (1, 2, 3)},
                               modelos={1: "d1", 2: "d2", 3: "d3"}, invocador_analisis=falla)
        resultado = panel.evaluar(_doc_sintetico(), None, ConfigEvaluacion(project_id="p-falla"))
        assert resultado.total == 92
        assert resultado.coherencia_global is None
