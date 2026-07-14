"""Tests obligatorios del agregador: mediana ordinal, discrepancia, ausencias,
normalización en modo progresivo y acuerdo del panel. Sin llamadas a OpenAI."""

from __future__ import annotations

import pytest

from graph.aggregator import agregar, mediana_inferior
from graph.schemas import (
    CalificacionDimension,
    CalificacionItemEscala,
    CalificacionItemPonderado,
    DIMENSIONES_TRANSVERSALES,
    RespuestaSeccionEscala,
    RespuestaSeccionPonderada,
    RespuestaTransversales,
    ResultadoJuez,
)
from graph.segmenter import ResultadoSegmentacion, SeccionSegmentada
from rubrics import load_rubric


@pytest.fixture(scope="module")
def rubrica():
    return load_rubric("especifica_v1")


@pytest.fixture(scope="module")
def ficha():
    return load_rubric("ficha_upao_v1")


def _segmentacion(rubrica, presentes: set[str]) -> ResultadoSegmentacion:
    return ResultadoSegmentacion(
        secciones=[
            SeccionSegmentada(
                seccion_id=s.id,
                nombre=s.nombre,
                presente=s.id in presentes,
                texto="texto de prueba " * 20 if s.id in presentes else "",
                palabras=60 if s.id in presentes else 0,
            )
            for s in rubrica.secciones
        ]
    )


def _juez(
    rubrica,
    numero: int,
    niveles: dict[str, str] | None = None,
    default: str = "cumple",
    presentes: set[str] | None = None,
    sin_secciones: set[str] | None = None,
    transversales: dict[str, int] | None = None,
) -> ResultadoJuez:
    niveles = niveles or {}
    secciones = {}
    huecos = []
    for seccion in rubrica.secciones:
        if presentes is not None and seccion.id not in presentes:
            continue
        if sin_secciones and seccion.id in sin_secciones:
            secciones[seccion.id] = None
            huecos.append(f"{seccion.id}: timeout simulado")
            continue
        secciones[seccion.id] = RespuestaSeccionPonderada(
            calificaciones=[
                CalificacionItemPonderado(
                    item_id=item.id,
                    deficiencias="ninguna",
                    nivel=niveles.get(item.id, default),
                    evidencia=f"«cita del juez {numero}» (sección {seccion.id})",
                    observacion=f"observación del juez {numero} para {item.id}",
                )
                for item in seccion.items
            ]
        )
    trans = transversales or {d: 4 for d in DIMENSIONES_TRANSVERSALES}
    return ResultadoJuez(
        juez=numero,
        modelo="doble-de-prueba",
        secciones=secciones,
        huecos=huecos,
        transversales=RespuestaTransversales(
            dimensiones=[
                CalificacionDimension(dimension=d, puntaje=p, justificacion=f"justificación juez {numero}")
                for d, p in trans.items()
            ]
        ),
    )


TODAS = {f"S{i:02d}" for i in range(1, 16)}


class TestMedianaOrdinal:
    @pytest.mark.parametrize(
        "niveles, esperado, discrepancia",
        [
            (("cumple", "parcial", "no_cumple"), "parcial", True),
            (("cumple", "cumple", "no_cumple"), "cumple", True),
            (("parcial", "parcial", "cumple"), "parcial", False),
            (("no_cumple", "parcial", "no_cumple"), "no_cumple", False),
            (("cumple", "cumple", "cumple"), "cumple", False),
        ],
    )
    def test_mediana_y_discrepancia_por_item(self, rubrica, niveles, esperado, discrepancia):
        seg = _segmentacion(rubrica, TODAS)
        jueces = [
            _juez(rubrica, n + 1, niveles={"1.1": nivel}) for n, nivel in enumerate(niveles)
        ]
        secciones, _, _, _ = agregar(rubrica, seg, jueces, "completo", TODAS)
        item = next(i for i in secciones[0].items if i.id == "1.1")
        assert item.nivel_final == esperado
        assert item.discrepancia is discrepancia
        assert item.niveles_jueces == {
            "juez1": niveles[0], "juez2": niveles[1], "juez3": niveles[2]
        }

    def test_mediana_inferior_con_panel_par(self):
        assert mediana_inferior([0, 2]) == 0
        assert mediana_inferior([1, 2]) == 1
        assert mediana_inferior([0, 1, 2]) == 1

    def test_puntaje_parcial_usa_el_valor_literal_de_la_tabla(self, rubrica):
        """Ítem 3.4: peso 0.75, parcial 0.38 (no 0.375)."""
        seg = _segmentacion(rubrica, TODAS)
        jueces = [_juez(rubrica, n, niveles={"3.4": "parcial"}) for n in (1, 2, 3)]
        secciones, _, _, _ = agregar(rubrica, seg, jueces, "completo", TODAS)
        item = next(i for i in secciones[2].items if i.id == "3.4")
        assert item.puntaje == 0.38

    def test_observacion_sintetizada_del_juez_mediano_y_marca_discrepancia(self, rubrica):
        seg = _segmentacion(rubrica, TODAS)
        jueces = [
            _juez(rubrica, 1, niveles={"1.1": "cumple"}),
            _juez(rubrica, 2, niveles={"1.1": "parcial"}),
            _juez(rubrica, 3, niveles={"1.1": "no_cumple"}),
        ]
        secciones, _, _, _ = agregar(rubrica, seg, jueces, "completo", TODAS)
        item = next(i for i in secciones[0].items if i.id == "1.1")
        # mediana = parcial → la observación proviene del juez 2 (sin inventar texto)
        assert "juez 2" in item.observacion
        assert item.observacion.startswith("[Discrepancia entre jueces]")
        assert "juez 2" in item.evidencia


class TestTotalesYModos:
    def test_todo_cumple_da_100(self, rubrica):
        seg = _segmentacion(rubrica, TODAS)
        jueces = [_juez(rubrica, n) for n in (1, 2, 3)]
        _, totales, _, panel = agregar(rubrica, seg, jueces, "completo", TODAS)
        assert totales["total"] == 100
        assert totales["nivel"] == "Excelente"
        assert panel.pct_discrepancia == 0
        assert panel.panel_incompleto is False

    def test_seccion_ausente_puntua_cero_con_observacion(self, rubrica):
        presentes = TODAS - {"S06"}
        seg = _segmentacion(rubrica, presentes)
        jueces = [_juez(rubrica, n, presentes=presentes) for n in (1, 2, 3)]
        secciones, totales, _, _ = agregar(rubrica, seg, jueces, "completo", TODAS)
        s06 = next(s for s in secciones if s.id == "S06")
        assert s06.presente is False and s06.subtotal == 0.0
        assert all(i.puntaje == 0 and "no encontrada" in i.observacion for i in s06.items)
        assert totales["total"] == 97  # 100 - 3 de S06

    def test_progresivo_normaliza_sobre_el_maximo_activo(self, rubrica):
        """S01+S03 activas (máx 10); S03 ausente → total 5, normalizado 50."""
        activas = {"S01", "S03"}
        presentes = TODAS - {"S03"}
        seg = _segmentacion(rubrica, presentes)
        jueces = [_juez(rubrica, n, presentes=activas & presentes) for n in (1, 2, 3)]
        secciones, totales, _, _ = agregar(rubrica, seg, jueces, "progresivo", activas)
        assert totales["puntaje_max_activo"] == 10
        assert totales["total"] == 5
        assert totales["total_normalizado"] == 50.0
        assert totales["nivel"] == "Insuficiente"  # 50 sobre escala 100
        inactivas = [s for s in secciones if not s.activa]
        assert len(inactivas) == 13
        assert all(s.subtotal is None and s.items == [] for s in inactivas)

    def test_progresivo_todo_cumple_normaliza_a_100(self, rubrica):
        activas = {"S01", "S02"}
        seg = _segmentacion(rubrica, TODAS)
        jueces = [_juez(rubrica, n, presentes=activas) for n in (1, 2, 3)]
        _, totales, _, _ = agregar(rubrica, seg, jueces, "progresivo", activas)
        assert totales["total"] == 15
        assert totales["total_normalizado"] == 100.0
        assert totales["nivel"] == "Excelente"


class TestSeccionVacia:
    def test_presente_pero_vacia_puntua_cero_con_observacion_honesta(self, rubrica):
        """Una sección con encabezado pero sin contenido evaluable no llega a los
        jueces: puntúa 0 con observación explícita (no 'falla de API')."""
        seg = _segmentacion(rubrica, TODAS)
        s06 = next(s for s in seg.secciones if s.seccion_id == "S06")
        s06.texto = "Ver anexo."
        s06.palabras = 2
        # Los jueces no calificaron S06 (la saltan por vacía)
        jueces = [_juez(rubrica, n, presentes=TODAS - {"S06"}) for n in (1, 2, 3)]
        secciones, totales, _, panel = agregar(rubrica, seg, jueces, "completo", TODAS)
        evaluada = next(s for s in secciones if s.id == "S06")
        assert evaluada.presente is True
        assert evaluada.subtotal == 0.0
        assert all("sin contenido evaluable" in i.observacion for i in evaluada.items)
        assert panel.panel_incompleto is False  # no es una falla de API
        assert totales["total"] == 97


class TestPanelIncompleto:
    def test_hueco_de_un_juez_usa_mediana_inferior_de_dos(self, rubrica):
        seg = _segmentacion(rubrica, TODAS)
        jueces = [
            _juez(rubrica, 1, niveles={"1.1": "cumple"}),
            _juez(rubrica, 2, sin_secciones={"S01"}),
            _juez(rubrica, 3, niveles={"1.1": "parcial"}),
        ]
        secciones, _, _, panel = agregar(rubrica, seg, jueces, "completo", TODAS)
        item = next(i for i in secciones[0].items if i.id == "1.1")
        # (cumple, parcial) → mediana inferior = parcial (conservador)
        assert item.nivel_final == "parcial"
        assert item.niveles_jueces["juez2"] is None
        assert panel.panel_incompleto is True
        assert any("S01" in h for h in panel.huecos)

    def test_pct_discrepancia(self, rubrica):
        seg = _segmentacion(rubrica, TODAS)
        jueces = [
            _juez(rubrica, 1),
            _juez(rubrica, 2),
            _juez(rubrica, 3, niveles={"1.1": "no_cumple", "2.1": "no_cumple"}),
        ]
        _, _, _, panel = agregar(rubrica, seg, jueces, "completo", TODAS)
        assert panel.items_marcados == ["S01.1.1", "S02.2.1"]
        assert panel.pct_discrepancia == round(2 / 85 * 100, 2)


class TestFichaUpao:
    """Escala directa 0-3 (ficha_upao_v1): mediana entera, nota vigesimal y
    exclusión de aspectos administrativos."""

    def _juez_escala(self, ficha, numero: int, puntajes: dict[str, int] | None = None,
                     default: int = 3) -> ResultadoJuez:
        puntajes = puntajes or {}
        return ResultadoJuez(
            juez=numero,
            modelo="doble-de-prueba",
            secciones={
                seccion.id: RespuestaSeccionEscala(
                    calificaciones=[
                        CalificacionItemEscala(
                            item_id=item.id,
                            deficiencias="ninguna",
                            puntaje=puntajes.get(item.id, default),
                            evidencia=f"«cita» ({seccion.id})",
                            observacion=f"obs juez {numero}",
                        )
                        for item in seccion.items
                    ]
                )
                for seccion in ficha.secciones
            },
        )

    def _todas(self, ficha):
        return {s.id for s in ficha.secciones}

    def test_todo_excelente_da_99_y_nota_20(self, ficha):
        seg = _segmentacion(ficha, self._todas(ficha))
        jueces = [self._juez_escala(ficha, n) for n in (1, 2, 3)]
        _, totales, _, _ = agregar(ficha, seg, jueces, "completo", self._todas(ficha))
        assert totales["puntaje_max_activo"] == 99
        assert totales["total"] == 99
        assert totales["nota_vigesimal"] == 20
        assert totales["total_normalizado"] is None

    def test_total_87_convierte_a_nota_18(self, ficha):
        """Fixture del plan: total 87 corresponde a nota vigesimal 18."""
        bajos = {"1": 0, "2": 0, "3": 0, "4": 0}  # 99 - 12 = 87
        seg = _segmentacion(ficha, self._todas(ficha))
        jueces = [self._juez_escala(ficha, n, puntajes=bajos) for n in (1, 2, 3)]
        _, totales, _, _ = agregar(ficha, seg, jueces, "completo", self._todas(ficha))
        assert totales["total"] == 87
        assert totales["nota_vigesimal"] == 18

    def test_mediana_entera_y_discrepancia_en_escala(self, ficha):
        seg = _segmentacion(ficha, self._todas(ficha))
        jueces = [
            self._juez_escala(ficha, 1, puntajes={"5": 3}),
            self._juez_escala(ficha, 2, puntajes={"5": 2}),
            self._juez_escala(ficha, 3, puntajes={"5": 0}),
        ]
        secciones, _, _, panel = agregar(ficha, seg, jueces, "completo", self._todas(ficha))
        item = next(i for s in secciones for i in s.items if i.id == "5")
        assert item.nivel_final == 2  # mediana de (3, 2, 0)
        assert item.puntaje == 2.0
        assert item.discrepancia is True  # rango 3 >= 2
        assert "B02.5" in panel.items_marcados

    def test_sin_administrativos_crudo_87_y_normalizado_100(self, ficha):
        """incluir_administrativos=false: crudo sobre 87 + normalizado a 100,
        sin nota vigesimal (la ficha no está completa)."""
        activas = self._todas(ficha) - {"B06"}
        seg = _segmentacion(ficha, self._todas(ficha))
        jueces = [self._juez_escala(ficha, n) for n in (1, 2, 3)]
        _, totales, _, _ = agregar(ficha, seg, jueces, "completo", activas)
        assert totales["puntaje_max_activo"] == 87
        assert totales["total"] == 87
        assert totales["total_normalizado"] == 100.0
        assert totales["nota_vigesimal"] is None


class TestTransversales:
    def test_mediana_y_justificacion_del_juez_mediano(self, rubrica):
        seg = _segmentacion(rubrica, TODAS)
        jueces = [
            _juez(rubrica, 1, transversales={d: 5 for d in DIMENSIONES_TRANSVERSALES}),
            _juez(rubrica, 2, transversales={d: 3 for d in DIMENSIONES_TRANSVERSALES}),
            _juez(rubrica, 3, transversales={d: 4 for d in DIMENSIONES_TRANSVERSALES}),
        ]
        _, _, transversales, _ = agregar(rubrica, seg, jueces, "completo", TODAS)
        assert [t.dimension for t in transversales] == list(DIMENSIONES_TRANSVERSALES)
        for t in transversales:
            assert t.mediana == 4
            assert "juez 3" in t.justificacion
            assert t.puntajes_jueces == {"juez1": 5, "juez2": 3, "juez3": 4}
