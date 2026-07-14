"""Tests del segmentador estructural (heurísticas, índice, ausentes, límites)."""

from __future__ import annotations

import pytest

from graph.segmenter import segmentar
from ingest.extractors import DocumentoExtraido, Pagina
from rubrics import load_rubric


def _parrafo(n: int) -> str:
    return " ".join(f"palabra{i}" for i in range(n))


def _doc_sintetico() -> DocumentoExtraido:
    """Proyecto sintético: carátula, índice y 13 de 15 secciones (faltan S06 y S10)."""
    paginas = [
        Pagina(numero=1, texto="UNIVERSIDAD PRIVADA ANTENOR ORREGO\nPROYECTO DE TESIS\n2026\n"),
        Pagina(
            numero=2,
            texto=(
                "ÍNDICE\n"
                "1. Título del proyecto .......... 3\n"
                "2. Descripción de la realidad problemática .......... 3\n"
                "3. Formulación del problema .......... 4\n"
                "4. Objetivos de la investigación .......... 4\n"
                "5. Marco teórico .......... 5\n"
            ),
        ),
        Pagina(
            numero=3,
            texto=(
                "1. TÍTULO DEL PROYECTO\n" + _parrafo(60) + "\n"
                "2. DESCRIPCIÓN DE LA REALIDAD PROBLEMÁTICA\n" + _parrafo(80) + "\n"
            ),
        ),
        Pagina(
            numero=4,
            texto=(
                "3. FORMULACIÓN DEL PROBLEMA\n" + _parrafo(55) + "\n"
                "4. OBJETIVOS DE LA INVESTIGACIÓN\n"
                "4.1 Objetivo general\n" + _parrafo(30) + "\n"
                "4.2 Objetivos específicos\n" + _parrafo(30) + "\n"
            ),
        ),
        Pagina(
            numero=5,
            texto=(
                "5. JUSTIFICACIÓN DEL ESTUDIO\n" + _parrafo(60) + "\n"
                "6. MARCO TEÓRICO\n"
                "6.1 Antecedentes de la investigación\n" + _parrafo(90) + "\n"
                "7. HIPÓTESIS\n" + _parrafo(55) + "\n"
            ),
        ),
        Pagina(
            numero=6,
            texto=(
                "8. VARIABLES Y OPERACIONALIZACIÓN\n" + _parrafo(60) + "\n"
                "9. TIPO Y MÉTODO DE INVESTIGACIÓN\n" + _parrafo(55) + "\n"
                "10. DISEÑO DEL ESTUDIO\n" + _parrafo(55) + "\n"
            ),
        ),
        Pagina(
            numero=7,
            texto=(
                "11. POBLACIÓN Y MUESTRA\n" + _parrafo(60) + "\n"
                "12. TÉCNICAS E INSTRUMENTOS DE RECOLECCIÓN DE DATOS\n" + _parrafo(55) + "\n"
                "13. TÉCNICAS DE PROCESAMIENTO Y ANÁLISIS DE DATOS\n"
                "Se usará el software SPSS para el análisis.\n"
                "REFERENCIAS BIBLIOGRÁFICAS\n"
                "Pérez, J. (2020). Un estudio previo. Editorial Académica.\n"
            ),
        ),
    ]
    return DocumentoExtraido(nombre="sintetico.pdf", tipo="pdf", paginas=paginas, paginacion_real=True)


@pytest.fixture(scope="module")
def resultado():
    return segmentar(_doc_sintetico(), load_rubric("especifica_v1"))


class TestSegmentador:
    def test_detecta_13_de_15_secciones(self, resultado):
        presentes = {s.seccion_id for s in resultado.presentes}
        assert len(presentes) == 13
        assert presentes == {f"S{i:02d}" for i in range(1, 16)} - {"S06", "S10"}

    def test_reporta_las_no_encontradas(self, resultado):
        assert any(s.startswith("S06") for s in resultado.no_encontradas)
        assert any(s.startswith("S10") for s in resultado.no_encontradas)

    def test_ignora_la_pagina_de_indice(self, resultado):
        assert resultado.paginas_indice == [2]
        s01 = next(s for s in resultado.secciones if s.seccion_id == "S01")
        assert s01.pagina_inicio == 3  # el encabezado real, no la línea del índice

    def test_paginas_y_palabras_coherentes(self, resultado):
        s02 = next(s for s in resultado.secciones if s.seccion_id == "S02")
        assert (s02.pagina_inicio, s02.pagina_fin) == (3, 3)
        assert s02.palabras >= 80
        s04 = next(s for s in resultado.secciones if s.seccion_id == "S04")
        # Incluye sus subsecciones 4.1 y 4.2 (los subencabezados no cortan)
        assert s04.palabras >= 60
        assert "Objetivos específicos" in s04.texto

    def test_las_referencias_cierran_la_ultima_seccion(self, resultado):
        s15 = next(s for s in resultado.secciones if s.seccion_id == "S15")
        assert "Editorial Académica" not in s15.texto

    def test_advierte_seccion_corta(self, resultado):
        assert any("S15" in a and "palabras" in a for a in resultado.advertencias)

    def test_reporte_serializable_sin_texto(self, resultado):
        reporte = resultado.reporte()
        assert len(reporte["secciones"]) == 15
        assert all("texto" not in fila for fila in reporte["secciones"])
        assert reporte["metodo"] == "heuristica"

    def test_fallback_llm_se_invoca_si_la_heuristica_falla(self):
        doc = DocumentoExtraido(
            nombre="plano.pdf",
            tipo="pdf",
            paginas=[Pagina(numero=1, texto=_parrafo(300))],  # sin encabezados
            paginacion_real=True,
        )
        rubrica = load_rubric("especifica_v1")
        invocado = {}

        def falso_llm(d, r):
            invocado["si"] = True
            resultado = segmentar(_doc_sintetico(), r)  # cualquier resultado
            resultado.metodo = "llm"
            return resultado

        resultado = segmentar(doc, rubrica, fallback_llm=falso_llm)
        assert invocado.get("si") is True
        assert resultado.metodo == "llm"

    def test_sin_fallback_advierte_segmentacion_pobre(self):
        doc = DocumentoExtraido(
            nombre="plano.pdf",
            tipo="pdf",
            paginas=[Pagina(numero=1, texto=_parrafo(300))],
            paginacion_real=True,
        )
        resultado = segmentar(doc, load_rubric("especifica_v1"))
        assert any("Segmentación pobre" in a for a in resultado.advertencias)


class TestFormatoUpaoReal:
    """Casos aprendidos del documento UPAO real (GENERALIDADES + contenedores)."""

    @staticmethod
    def _doc_upao() -> DocumentoExtraido:
        paginas = [
            Pagina(
                numero=1,
                texto=(
                    "I. GENERALIDADES\n"
                    "1. Título\n"
                    "Sistema multiagente y su efecto en la calidad metodológica.\n"
                    "3. Tipo de investigación\n"
                    "Aplicada.\n"
                    "4. Línea de investigación\n"
                    "Sistemas inteligentes.\n"
                ),
            ),
            Pagina(
                numero=2,
                texto=(
                    "II. PLAN DE INVESTIGACIÓN\n"
                    "1.1. Descripción y delimitación del problema\n"
                    "1.1.1. Formulación del problema\n" + _parrafo(70) + "\n"
                    "1.1.2. Problema central del estudio\n" + _parrafo(40) + "\n"
                    "1.2. Objetivos de la investigación\n" + _parrafo(55) + "\n"
                ),
            ),
            Pagina(
                numero=3,
                texto=(
                    "3. HIPÓTESIS Y VARIABLES\n"
                    "3.1. Supuestos básicos\n" + _parrafo(45) + "\n"
                    "3.1.1. Hipótesis general\n" + _parrafo(25) + "\n"
                    "3.2. Variables y operacionalización\n" + _parrafo(55) + "\n"
                ),
            ),
            Pagina(
                numero=4,
                texto=(
                    "4. MARCO METODOLÓGICO\n"
                    "4.1. Tipo y método de investigación\n" + _parrafo(60) + "\n"
                    "4.4. Población y muestra\n" + _parrafo(55) + "\n"
                    "REFERENCIAS BIBLIOGRÁFICAS\nPérez, J. (2020). Estudio previo.\n"
                ),
            ),
        ]
        return DocumentoExtraido(nombre="upao.pdf", tipo="pdf", paginas=paginas, paginacion_real=True)

    @pytest.fixture(scope="class")
    @staticmethod
    def resultado():
        return segmentar(TestFormatoUpaoReal._doc_upao(), load_rubric("especifica_v1"))

    def test_encabezado_contenedor_absorbe_sus_subsecciones(self, resultado):
        """'1.1. Descripción...' no tiene cuerpo directo: absorbe 1.1.1 y 1.1.2."""
        s02 = next(s for s in resultado.secciones if s.seccion_id == "S02")
        assert s02.presente
        assert s02.palabras >= 110  # 70 + 40 de sus subsecciones
        assert any("contenedor" in a for a in resultado.advertencias)
        # La formulación (S03) conserva su propio texto (spans solapados)
        s03 = next(s for s in resultado.secciones if s.seccion_id == "S03")
        assert s03.palabras >= 70

    def test_desempate_prefiere_el_encabezado_en_orden_del_documento(self, resultado):
        """'Tipo de investigación' aparece en GENERALIDADES (pág. 1) y en el
        marco metodológico (pág. 4): gana el que respeta el orden."""
        s11 = next(s for s in resultado.secciones if s.seccion_id == "S11")
        assert s11.pagina_inicio == 4
        assert s11.palabras >= 55

    def test_capitulo_hipotesis_incluye_los_supuestos(self, resultado):
        """El alias 'hipótesis y variables' ancla S08 en el capítulo completo."""
        s08 = next(s for s in resultado.secciones if s.seccion_id == "S08")
        assert s08.pagina_inicio == 3
        assert "Supuestos" in s08.texto or s08.palabras >= 65
