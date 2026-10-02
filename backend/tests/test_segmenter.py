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


class TestPlantillaDocxSinNumeracion:
    """Plantilla UPAO extraída de DOCX (caso real 'gestión de gastos'): la
    numeración automática de Word no sobrevive a la extracción y la matriz de
    consistencia contiene rótulos ("Tipo de investigación:") que empatan con
    los aliases y aparecen ANTES que los encabezados reales."""

    @staticmethod
    def _doc() -> DocumentoExtraido:
        pagina1 = (
            "PLAN DE INVESTIGACIÓN\n"
            "PLANTEAMIENTO DEL ESTUDIO\n"
            "Descripción y delimitación del problema\n"
            "Formulación del problema\n"
            "¿De qué manera un sistema web influye en la mejora de la gestión de gastos?\n"
            "Problema central del estudio\n" + _parrafo(80) + "\n"
            "Objetivos\n" + _parrafo(40) + "\n"
            "Justificación del estudio\n" + _parrafo(45) + "\n"
        )
        pagina2 = (
            "Matriz de consistencia\n"
            "Problema general | Objetivo general | Hipótesis general | Variables | Indicadores | Metodología\n"
            "Tipo de investigación: \n"
            "Aplicada\n"
            "Diseño de investigación:\n"
            "Experimental puro\n"
            "Población:\n"
            "Todos los procesos de registro de gastos\n"
            "MARCO METODOLÓGICO\n"
            "Tipo de investigación\n" + _parrafo(60) + "\n"
            "Diseño del estudio\n" + _parrafo(55) + "\n"
            "Población y muestra\n" + _parrafo(50) + "\n"
            "Técnicas e instrumentos de recolección de datos\n" + _parrafo(40) + "\n"
        )
        return DocumentoExtraido(
            nombre="upao.docx",
            tipo="docx",
            paginas=[Pagina(numero=1, texto=pagina1), Pagina(numero=2, texto=pagina2)],
            paginacion_real=False,
        )

    @pytest.fixture(scope="class")
    @staticmethod
    def resultado():
        return segmentar(TestPlantillaDocxSinNumeracion._doc(), load_rubric("especifica_v1"))

    def test_rotulos_de_la_matriz_no_secuestran_las_secciones(self, resultado):
        """S11/S12/S13 deben anclarse en los encabezados reales del marco
        metodológico, no en los rótulos de la matriz (que dejaban 1-5 palabras)."""
        s11 = next(s for s in resultado.secciones if s.seccion_id == "S11")
        assert s11.encontrado_como == "Tipo de investigación"
        assert s11.palabras >= 60
        s12 = next(s for s in resultado.secciones if s.seccion_id == "S12")
        assert s12.encontrado_como == "Diseño del estudio"
        assert s12.palabras >= 55
        s13 = next(s for s in resultado.secciones if s.seccion_id == "S13")
        assert s13.encontrado_como == "Población y muestra"
        assert s13.palabras >= 50

    def test_la_matriz_conserva_su_contenido(self, resultado):
        s10 = next(s for s in resultado.secciones if s.seccion_id == "S10")
        assert "Experimental puro" in s10.texto

    def test_problema_central_repara_la_descripcion_vacia(self, resultado):
        """Sin numeración no hay absorción jerárquica: S02 quedaba en 0 palabras
        y el contenido real (bajo 'Problema central del estudio') se iba a S03.
        La reparación por contenido reasigna S02 y S03 conserva solo la pregunta."""
        s02 = next(s for s in resultado.secciones if s.seccion_id == "S02")
        assert s02.encontrado_como == "Problema central del estudio"
        assert s02.palabras >= 80
        s03 = next(s for s in resultado.secciones if s.seccion_id == "S03")
        assert s03.presente
        assert "¿De qué manera" in s03.texto
        assert s03.palabras < 20
        assert any("se reasignó" in a for a in resultado.advertencias)


class TestTituloInlineYFormulacionSinL:
    """Caso real ('PT_Agreda ... Pan-CK'): el TÍTULO va como rótulo con su valor
    en la misma línea (>90 caracteres, nunca es candidato a encabezado) → se
    recupera como caso especial aditivo. La FORMULACIÓN usa la variante 'Formulación
    DE problema' (sin la 'l' de 'del') → la resuelve _puntuar colapsando 'del'↔'de'.
    Ninguna toca la detección de las demás secciones."""

    _TITULO = (
        "Evaluación comparativa de la concordancia en la identificación de células "
        "epiteliales positivas a Pan-CK entre Visión Computacional y Gold Standard"
    )

    @staticmethod
    def _doc() -> DocumentoExtraido:
        pagina1 = (
            "UNIVERSIDAD PRIVADA ANTENOR ORREGO\n"
            f"\tTítulo: {TestTituloInlineYFormulacionSinL._TITULO}\n"
            "\tAutores:\n"
            "\tFulano De Tal\n"
        )
        pagina2 = (
            "PLAN DE INVESTIGACIÓN\n"
            "PLANTEAMIENTO DEL ESTUDIO\n"
            "\t1.1. Descripción y delimitación del problema\n" + _parrafo(80) + "\n"
            "\t1.1.1. Formulación de problema.\n"
            "\t¿Cuál es el nivel de concordancia entre un sistema de visión computacional "
            'y el "gold standard" para la identificación de células epiteliales positivas '
            "a Pan-CK en láminas de inmunohistoquímica?\n"
            "\t1.1.2. Problema central del estudio.\n" + _parrafo(40) + "\n"
            "\tObjetivos de la Investigación:\n"
            "Objetivo General\n" + _parrafo(55) + "\n"
            "Importancia del estudio.\n" + _parrafo(60) + "\n"
            "Limitaciones del estudio.\n" + _parrafo(40) + "\n"
            "MARCO TEÓRICO\n" + _parrafo(90) + "\n"
            "HIPÓTESIS Y VARIABLES\n" + _parrafo(55) + "\n"
            "Variables y operacionalización\n" + _parrafo(50) + "\n"
            "Matriz de consistencia\n" + _parrafo(40) + "\n"
            "Tipo y método de investigación\n" + _parrafo(55) + "\n"
            "Diseño del estudio\n" + _parrafo(55) + "\n"
            "Población y muestra\n" + _parrafo(50) + "\n"
        )
        return DocumentoExtraido(
            nombre="pancck.docx",
            tipo="docx",
            paginas=[Pagina(numero=1, texto=pagina1), Pagina(numero=2, texto=pagina2)],
            paginacion_real=False,
        )

    @pytest.fixture(scope="class")
    @staticmethod
    def resultado():
        return segmentar(TestTituloInlineYFormulacionSinL._doc(), load_rubric("especifica_v1"))

    def test_titulo_inline_se_recupera(self, resultado):
        s01 = next(s for s in resultado.secciones if s.seccion_id == "S01")
        assert s01.presente
        assert s01.encontrado_como == "Título"
        assert s01.texto == TestTituloInlineYFormulacionSinL._TITULO
        assert any(a.startswith("S01") and "rótulo" in a for a in resultado.advertencias)

    def test_formulacion_sin_l_se_detecta_por_tolerancia_del_de(self, resultado):
        """'Formulación de problema' (sin 'l') empata con el alias 'formulación
        del problema' gracias a que _puntuar colapsa 'del'↔'de'."""
        s03 = next(s for s in resultado.secciones if s.seccion_id == "S03")
        assert s03.presente
        assert s03.encontrado_como == "Formulación de problema"
        assert s03.texto.startswith("¿Cuál es el nivel de concordancia")


class TestNumeracionPegadaYDelDe:
    """Caso real ('PT_Ramos Cotrina y Yepez Zapata.pdf'): la extracción PDF pierde
    el espacio tras la numeración ('1.3.Importancia', '4.3.Diseño de estudio'), lo
    que ocultaba S05/S06 y desanclaba S12. Además los encabezados usan 'de' donde la
    rúbrica dice 'del' ('Diseño DE estudio'). Ambos se resuelven sin caso especial:
    las regex de numeración aceptan el terminador pegado a la letra y _puntuar
    colapsa 'del'↔'de'."""

    @staticmethod
    def _doc() -> DocumentoExtraido:
        pagina1 = (
            "GENERALIDADES\n"
            "Título\n"
            "Sistema Web Inteligente y su efecto, Trujillo 2026\n"
            "3.1.De acuerdo a la orientación o finalidad: aplicada\n"
            "Tipo de Investigación\n"  # mención temprana en GENERALIDADES
        )
        pagina2 = (
            "PLAN DE INVESTIGACIÓN\n"
            "1.1.Descripción y delimitación del Problema\n" + _parrafo(80) + "\n"
            "1.1.1.Formulación de problema\n"
            "¿De qué manera un Sistema Web Inteligente mejora la gestión?\n"
            "1.2.Objetivos de la investigación\n" + _parrafo(55) + "\n"
            "1.3.Importancia del estudio\n" + _parrafo(60) + "\n"
            "1.4.Justificación del estudio\n" + _parrafo(50) + "\n"
            "1.5.Limitaciones del estudio\n" + _parrafo(40) + "\n"
            "2.Marco Teórico\n" + _parrafo(90) + "\n"
            "3.Hipótesis y variables\n" + _parrafo(50) + "\n"
            "3.2.Operacionalización de las variables\n" + _parrafo(50) + "\n"
            "Matriz de consistencia\n" + _parrafo(40) + "\n"
        )
        pagina3 = (
            "4.Marco Metodológico\n"
            "4.1.Tipo de investigación\n" + _parrafo(50) + "\n"
            "4.3.Diseño de estudio\n" + _parrafo(50) + "\n"
            "4.4.Población y muestra\n" + _parrafo(50) + "\n"
            "4.5.Técnicas e instrumentos de recolección de datos\n" + _parrafo(40) + "\n"
            "4.7.Técnicas de procesamiento y análisis de datos\n" + _parrafo(40) + "\n"
            "Cronograma\n"
            "●\n"
            "Formulación y diseño del estudio\n"  # bullet del cronograma: falso S12
            "Preparación del estudio\n"
        )
        return DocumentoExtraido(
            nombre="ramos.pdf", tipo="pdf",
            paginas=[Pagina(numero=1, texto=pagina1), Pagina(numero=2, texto=pagina2),
                     Pagina(numero=3, texto=pagina3)],
            paginacion_real=True,
        )

    @pytest.fixture(scope="class")
    @staticmethod
    def resultado():
        return segmentar(TestNumeracionPegadaYDelDe._doc(), load_rubric("especifica_v1"))

    def test_todas_las_secciones_presentes(self, resultado):
        assert not resultado.no_encontradas

    def test_secciones_pegadas_al_numero_se_detectan(self, resultado):
        """'1.3.Importancia' y '1.5.Limitaciones' (sin espacio tras el número)."""
        s05 = next(s for s in resultado.secciones if s.seccion_id == "S05")
        s06 = next(s for s in resultado.secciones if s.seccion_id == "S06")
        assert s05.presente and s05.encontrado_como == "Importancia del estudio"
        assert s06.presente and s06.encontrado_como == "Limitaciones del estudio"

    def test_diseno_de_estudio_gana_al_bullet_del_cronograma(self, resultado):
        """S12 ancla en '4.3.Diseño de estudio' (variante 'de', numerada) y no en
        el bullet 'Formulación y diseño del estudio' del cronograma."""
        s12 = next(s for s in resultado.secciones if s.seccion_id == "S12")
        assert s12.encontrado_como == "Diseño de estudio"
        assert s12.pagina_inicio == 3

    def test_metodologia_en_orden_sin_advertencias(self, resultado):
        """S11→S15 quedan en orden de página (S11 ancla en el '4.1' tardío, no en
        la mención de GENERALIDADES), así que no hay avisos de orden."""
        metodo = [s for s in resultado.secciones if s.seccion_id in
                  {"S11", "S12", "S13", "S14", "S15"}]
        paginas = [s.pagina_inicio for s in metodo]
        assert paginas == sorted(paginas)
        assert not any("fuera del orden" in a for a in resultado.advertencias)
