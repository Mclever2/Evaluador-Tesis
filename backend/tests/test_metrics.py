"""Tests de las métricas determinísticas (sin LLM)."""

from __future__ import annotations

import pytest

from graph.segmenter import ResultadoSegmentacion, SeccionSegmentada
from ingest.extractors import DocumentoExtraido, Pagina
from metrics.deterministic import (
    _citas_referencias,
    _longitud_media_oracion,
    _riqueza_lexica,
    calcular_metricas,
)

CUERPO = (
    "La investigación aborda la gestión de inventarios. Según García (2020), los "
    "sistemas web reducen las pérdidas operativas. Estudios recientes coinciden "
    "(Pérez et al., 2018; Díaz, 2021). Otros autores discrepan del enfoque "
    "propuesto, como sostiene López (2019) en su análisis regional. "
    "El marco sigue la ruta cuantitativa de Hernández (2018) para el diseño. "
) * 3

# Nota: la entrada de Pérez está partida en dos líneas (como en los PDF reales)
# y Hernández-Sampieri se cita en el cuerpo solo como "Hernández (2018)".
REFERENCIAS = """REFERENCIAS BIBLIOGRÁFICAS
García, M. (2020). Sistemas web de inventario. Editorial Andina.
Pérez, J., Ruiz, A. y Soto, C.
(2018). Logística digital. McGraw-Hill.
Hernández-Sampieri, R. y Mendoza, C. (2018). Metodología de la investigación. McGraw-Hill.
Ramos, T. (2015). Almacenes modernos. Editorial Sur.
ANEXOS
Anexo 1: instrumentos.
"""


def _doc() -> DocumentoExtraido:
    return DocumentoExtraido(
        nombre="m.pdf",
        tipo="pdf",
        paginas=[Pagina(numero=1, texto=CUERPO), Pagina(numero=2, texto=REFERENCIAS)],
        paginacion_real=True,
    )


def _segmentacion() -> ResultadoSegmentacion:
    secciones = [
        SeccionSegmentada(
            seccion_id="S01", nombre="Título", presente=True,
            texto=CUERPO, palabras=len(CUERPO.split()),
        )
    ] + [
        SeccionSegmentada(seccion_id=f"S{i:02d}", nombre=f"Sección {i}", presente=False)
        for i in range(2, 16)
    ]
    return ResultadoSegmentacion(secciones=secciones)


@pytest.fixture(scope="module")
def citas():
    return _citas_referencias(CUERPO, CUERPO + "\n" + REFERENCIAS)


class TestCitasReferencias:
    def test_detecta_citas_narrativas_y_parenteticas(self, citas):
        # García, Pérez et al., Díaz, López, Hernández
        assert citas.citas_en_texto == 5

    def test_detecta_referencias_incluso_partidas_en_varias_lineas(self, citas):
        # García, Pérez (entrada en dos líneas), Hernández-Sampieri, Ramos
        assert citas.referencias_en_lista == 4

    def test_inconsistencias_con_apellidos_compuestos(self, citas):
        # "Hernández (2018)" empareja con "Hernández-Sampieri (2018)"
        assert citas.citas_sin_referencia == ["díaz (2021)", "lópez (2019)"]
        assert citas.referencias_nunca_citadas == ["ramos (2015)"]
        assert citas.aproximado is True

    def test_apellido_compuesto_empareja_por_cualquier_token(self):
        """La cita narrativa no siempre captura el primer apellido del compuesto:
        'Zéniz Ramos et al. (2024)' se extrae como 'ramos (2024)' y debe
        emparejar con la entrada 'Zéniz Ramos, D. F.' (caso real)."""
        cuerpo = (
            "En la investigación de Zéniz Ramos et al. (2024) se evaluó un sistema web. "
            "El estudio confirma el enfoque aplicado (Maldonado et al., 2023). "
            "Según Intriago et al. (2020), la gestión mejora con control financiero. "
        )
        referencias = (
            "REFERENCIAS BIBLIOGRÁFICAS\n"
            "Castro Maldonado, J. J. (2023). La investigación aplicada. Tecnura.\n"
            "López-Intriago, C. F. (2020). Gestión financiera. Koinonía.\n"
            "Zéniz Ramos, D. F. (2024). Sistema web comercial. Innovación y Software.\n"
        )
        citas = _citas_referencias(cuerpo, cuerpo + "\n" + referencias)
        assert citas.citas_sin_referencia == []
        assert citas.referencias_nunca_citadas == []


class TestLegibilidadYLexico:
    def test_legibilidad_en_rangos_plausibles(self):
        metricas = calcular_metricas(_doc(), _segmentacion())
        assert metricas.legibilidad.fernandez_huerta is not None
        assert 0 <= metricas.legibilidad.fernandez_huerta <= 120
        assert 0 <= metricas.legibilidad.szigriszt_pazos <= 120
        assert metricas.legibilidad.interpretacion is not None

    def test_riqueza_lexica(self):
        tokens_diversos = " ".join(f"palabra{i} termino{i} concepto{i}" for i in range(40))
        repetitivo = "dato " * 120
        diverso = _riqueza_lexica(tokens_diversos)
        pobre = _riqueza_lexica(repetitivo)
        assert diverso.ttr > pobre.ttr
        assert diverso.mtld > pobre.mtld
        assert pobre.ttr == round(1 / 120, 4)

    def test_longitud_media_oracion(self):
        texto = "Una oración con cinco palabras aquí. Otra oración corta de prueba."
        media = _longitud_media_oracion(texto)
        assert media == pytest.approx(5.5, abs=0.6)


class TestIntegracion:
    def test_metricas_completas(self):
        metricas = calcular_metricas(_doc(), _segmentacion())
        assert metricas.completitud.presentes == 1
        assert metricas.completitud.total == 15
        assert metricas.palabras_por_seccion["S01"] > 0
        assert metricas.palabras_totales == len(CUERPO.split())
        assert metricas.longitud_media_oracion is not None
