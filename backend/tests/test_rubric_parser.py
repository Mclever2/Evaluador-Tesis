"""Tests del parser de rúbricas (verificación obligatoria del plan).

especifica_v1: máximos por sección exactamente 5, 10, 5, 8, 7, 3, 12, 8, 8,
5, 5, 8, 8, 5, 3 y suma 100. ficha_upao_v1: 33 ítems, máximo 99, bloques y
conversión vigesimal (87 → 18); esos tests se activan cuando el autor entregue
docs/ficha_upao.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rubrics import RUBRICS_DIR
from rubrics.parser import parse_especifica, parse_ficha_upao

ROOT = Path(__file__).resolve().parents[2]
FUENTE_ESPECIFICA = ROOT / "docs" / "rubrica_especifica.md"
FUENTE_FICHA = ROOT / "docs" / "ficha_upao.md"

MAXIMOS_ESPERADOS = [5, 10, 5, 8, 7, 3, 12, 8, 8, 5, 5, 8, 8, 5, 3]


@pytest.fixture(scope="module")
def parseo():
    return parse_especifica(FUENTE_ESPECIFICA.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rubrica(parseo):
    return parseo[0]


class TestEspecificaV1:
    def test_quince_secciones_con_ids_secuenciales(self, rubrica):
        assert [s.id for s in rubrica.secciones] == [f"S{i:02d}" for i in range(1, 16)]

    def test_maximos_por_seccion(self, rubrica):
        assert [s.puntaje_max for s in rubrica.secciones] == MAXIMOS_ESPERADOS

    def test_total_100(self, rubrica):
        assert rubrica.puntaje_maximo == 100

    def test_escala_tres_niveles(self, rubrica):
        assert rubrica.tipo == "ponderada_3_niveles"
        assert rubrica.escala == {"cumple": 1.0, "parcial": 0.5, "no_cumple": 0.0}

    def test_pesos_de_items_suman_el_maximo_declarado(self, rubrica):
        # El 2026-07-12 el autor corrigió la fuente (ítem 7.4: 0.5 → 1.0) para
        # que S07 sume su máximo declarado de 12.
        for seccion in rubrica.secciones:
            assert seccion.suma_pesos() == round(seccion.puntaje_max, 2), seccion.id

    def test_parseo_sin_advertencias(self, parseo):
        _, advertencias = parseo
        assert advertencias == []

    def test_parciales_literales_de_la_tabla(self, rubrica):
        """El valor de 'parcial' se respeta tal cual (con sus redondeos)."""
        esperados = {
            ("S03", "3.4"): (0.75, 0.38),
            ("S07", "7.4"): (1.0, 0.5),
            ("S12", "12.1"): (2.0, 1.0),
            ("S01", "1.1"): (1.0, 0.5),
        }
        for (sid, iid), (peso, parcial) in esperados.items():
            item = next(i for i in rubrica.seccion(sid).items if i.id == iid)
            assert (item.peso, item.parcial) == (peso, parcial), (sid, iid)

    def test_niveles_de_calidad_continuos(self, rubrica):
        etiquetas = {n.etiqueta: n for n in rubrica.niveles_calidad}
        assert set(etiquetas) == {"Excelente", "Bueno", "Regular", "Insuficiente"}
        assert (etiquetas["Excelente"].min, etiquetas["Excelente"].max) == (90, 100)
        assert (etiquetas["Bueno"].min, etiquetas["Bueno"].max) == (75, 89.99)
        assert (etiquetas["Regular"].min, etiquetas["Regular"].max) == (60, 74.99)
        assert (etiquetas["Insuficiente"].min, etiquetas["Insuficiente"].max) == (0, 59.99)

    @pytest.mark.parametrize(
        "total, etiqueta",
        [
            (100, "Excelente"), (90, "Excelente"), (89.5, "Bueno"), (75, "Bueno"),
            (74.99, "Regular"), (60, "Regular"), (59.99, "Insuficiente"), (0, "Insuficiente"),
        ],
    )
    def test_nivel_para_total(self, rubrica, total, etiqueta):
        assert rubrica.nivel_para(total) == etiqueta

    def test_items_tienen_criterio_y_referencia(self, rubrica):
        for seccion in rubrica.secciones:
            for item in seccion.items:
                assert len(item.criterio) > 20, item.id
                assert item.referencia and item.referencia.startswith("HS2018"), item.id

    def test_todas_las_secciones_tienen_aliases_normalizados(self, rubrica):
        from rubrics.parser import normalizar

        for seccion in rubrica.secciones:
            assert seccion.aliases, seccion.id
            for alias in seccion.aliases:
                assert alias == normalizar(alias), alias  # minúsculas, sin tildes ni ñ

    def test_json_versionado_en_sincronia_con_la_fuente(self, rubrica):
        """backend/rubrics/especifica_v1.json debe ser exactamente lo que
        produce el parser sobre docs/ (regenerar con python -m cli.build_rubrics)."""
        ruta = RUBRICS_DIR / "especifica_v1.json"
        assert ruta.exists(), "Falta especifica_v1.json: correr python -m cli.build_rubrics"
        versionado = json.loads(ruta.read_text(encoding="utf-8"))
        actual = json.loads(rubrica.model_dump_json(exclude_none=True))
        assert versionado == actual


class TestFichaUpaoV1:
    """Se activan cuando el autor entregue docs/ficha_upao.md (33 ítems + tabla)."""

    pendiente = pytest.mark.skipif(
        not FUENTE_FICHA.exists(),
        reason="docs/ficha_upao.md aún no entregado por el autor (no se inventan ítems)",
    )

    BLOQUES_ESPERADOS = {
        "Título": (1, 3),
        "Planteamiento del problema": (4, 10),
        "Marco teórico": (11, 17),
        "Hipótesis y variables": (18, 21),
        "Marco metodológico": (22, 27),
        "Aspectos administrativos": (28, 31),
        "Referencias bibliográficas": (32, 33),
    }

    @pytest.fixture(scope="class")
    def ficha(self):
        rubrica, _ = parse_ficha_upao(FUENTE_FICHA.read_text(encoding="utf-8"))
        return rubrica

    @pendiente
    def test_33_items_maximo_99(self, ficha):
        assert ficha.total_items == 33
        assert ficha.puntaje_maximo == 99

    @pendiente
    def test_bloques(self, ficha):
        assert len(ficha.secciones) == len(self.BLOQUES_ESPERADOS)
        for seccion, (nombre, (desde, hasta)) in zip(
            ficha.secciones, self.BLOQUES_ESPERADOS.items()
        ):
            ids = [int(i.id) for i in seccion.items]
            assert ids == list(range(desde, hasta + 1)), nombre

    @pendiente
    def test_conversion_vigesimal_87_es_18(self, ficha):
        assert ficha.nota_vigesimal(87) == 18

    def test_parser_ficha_exige_la_fuente(self):
        if FUENTE_FICHA.exists():
            pytest.skip("La fuente ya existe; este guard aplica solo mientras falte.")
        with pytest.raises(NotImplementedError):
            parse_ficha_upao("")
