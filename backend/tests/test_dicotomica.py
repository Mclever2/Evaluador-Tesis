"""Rúbrica dicotómica v2 (100 ítems) y limpieza de la plantilla UPAO.
Sin llamadas a OpenAI."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from graph.aggregator import agregar
from graph.prompts import render_prompt_juez
from graph.schemas import (
    CalificacionItemDicotomico,
    RespuestaSeccionDicotomica,
    ResultadoJuez,
)
from graph.segmenter import ResultadoSegmentacion, SeccionSegmentada
from ingest.plantilla import limpiar_texto, palabras_propias
from rubrics import load_rubric
from rubrics.parser import parse_dicotomica

DOCS = Path(__file__).resolve().parents[2] / "docs"


@pytest.fixture(scope="module")
def rubrica():
    return load_rubric("dicotomica_v2")


def _segmentacion(rubrica, presentes: set[str]) -> ResultadoSegmentacion:
    return ResultadoSegmentacion(
        secciones=[
            SeccionSegmentada(
                seccion_id=s.id, nombre=s.nombre, presente=s.id in presentes,
                texto="texto de prueba " * 20 if s.id in presentes else "",
                palabras=40 if s.id in presentes else 0,
            )
            for s in rubrica.secciones
        ]
    )


def _juez(rubrica, numero: int, niveles: dict[str, str], presentes: set[str]) -> ResultadoJuez:
    secciones = {}
    for seccion in rubrica.secciones:
        if seccion.id not in presentes:
            continue
        secciones[seccion.id] = RespuestaSeccionDicotomica(
            calificaciones=[
                CalificacionItemDicotomico(
                    item_id=item.id, verificacion="v", deficiencias="ninguna",
                    nivel=niveles.get(item.id, "no_cumple"),
                    evidencia="cita", observacion=f"juez{numero}",
                )
                for item in seccion.items
            ]
        )
    return ResultadoJuez(juez=numero, modelo="doble", secciones=secciones)


class TestParser:
    def test_fuente_produce_15_dimensiones_y_100_items(self):
        rub, advertencias = parse_dicotomica((DOCS / "rubrica_dicotomica_v2.md").read_text(encoding="utf-8"))
        assert advertencias == []
        assert rub.tipo == "dicotomica"
        assert len(rub.secciones) == 15 and rub.total_items == 100
        assert rub.puntaje_maximo == 100
        assert [len(s.items) for s in rub.secciones] == [5, 8, 5, 7, 6, 3, 12, 6, 9, 4, 5, 7, 8, 8, 7]
        assert all(i.peso == 1 and i.parcial is None for s in rub.secciones for i in s.items)

    def test_json_versionado_coincide_con_la_fuente(self, rubrica):
        rub, _ = parse_dicotomica((DOCS / "rubrica_dicotomica_v2.md").read_text(encoding="utf-8"))
        assert rub.model_dump() == rubrica.model_dump()


class TestEsquema:
    def test_parcial_no_es_un_nivel_valido(self):
        with pytest.raises(ValidationError):
            CalificacionItemDicotomico(
                item_id="1.1", verificacion="v", deficiencias="x", nivel="parcial", evidencia="", observacion=""
            )


class TestAgregadorDicotomico:
    def test_voto_de_mayoria_y_discrepancia_no_unanime(self, rubrica):
        presentes = {"S01"}
        jueces = [
            _juez(rubrica, 1, {"1.1": "cumple", "1.2": "cumple", "1.3": "cumple"}, presentes),
            _juez(rubrica, 2, {"1.1": "cumple", "1.2": "cumple"}, presentes),
            _juez(rubrica, 3, {"1.1": "cumple"}, presentes),
        ]
        secciones, totales, _, panel = agregar(
            rubrica, _segmentacion(rubrica, presentes), jueces, "completo", {s.id for s in rubrica.secciones}
        )
        items = {i.id: i for i in secciones[0].items}
        assert items["1.1"].puntaje == 1 and not items["1.1"].discrepancia  # 3-0
        assert items["1.2"].puntaje == 1 and items["1.2"].discrepancia      # 2-1 → cumple
        assert items["1.3"].puntaje == 0 and items["1.3"].discrepancia      # 1-2 → no cumple
        assert items["1.4"].puntaje == 0 and not items["1.4"].discrepancia  # 0-3
        assert totales["total"] == 2
        assert totales["nivel"] is None  # la rúbrica no define bandas de calidad
        assert panel.pct_discrepancia == 40.0  # 2 de 5 ítems evaluados

    def test_hueco_en_panel_exige_ambos_votos(self, rubrica):
        presentes = {"S01"}
        jueces = [
            _juez(rubrica, 1, {"1.1": "cumple", "1.2": "cumple"}, presentes),
            _juez(rubrica, 2, {"1.1": "cumple"}, presentes),
        ]
        secciones, _, _, _ = agregar(
            rubrica, _segmentacion(rubrica, presentes), jueces, "completo", {s.id for s in rubrica.secciones}
        )
        items = {i.id: i for i in secciones[0].items}
        assert items["1.1"].puntaje == 1
        assert items["1.2"].puntaje == 0  # empate 1-1 → mediana inferior (conservador)

    def test_dimensiones_ausentes_puntuan_cero(self, rubrica):
        secciones, totales, _, _ = agregar(
            rubrica, _segmentacion(rubrica, set()), [], "completo", {s.id for s in rubrica.secciones}
        )
        assert totales["total"] == 0 and totales["puntaje_max_activo"] == 100
        assert all(i.nivel_final == "no_cumple" for s in secciones for i in s.items)


class TestPrompt:
    def test_prompt_dicotomico_sin_nivel_parcial(self, rubrica):
        prompt = render_prompt_juez("rol", rubrica, rubrica.secciones[0], "texto")
        assert "VERIFICACIÓN DICOTÓMICA" in prompt
        assert "EN CONSTRUCCIÓN" in prompt
        assert "[1.1]" in prompt and "[1.5]" in prompt
        assert "- parcial:" not in prompt  # la escala de 3 niveles no aparece


class TestPlantilla:
    RELLENO = (
        "El texto expositivo es aquel texto que ofrece al lector una información\n"
        "explícita sobre un tema puntual, de manera objetiva, es decir, sin que\n"
        "medie en ningún momento la opinión del autor o sus posicionamientos. En\n"
        "consecuencia, tampoco necesita utilizar argumentaciones para convencer."
    )

    def test_quita_relleno_con_saltos_de_linea(self):
        texto, n = limpiar_texto("1.3. Importancia del estudio\n" + self.RELLENO)
        assert n == 2
        assert "expositivo" not in texto and "Importancia del estudio" in texto

    def test_conserva_texto_del_estudiante_mezclado(self):
        texto, _ = limpiar_texto("¿En qué medida el modelo mejora la precisión? " + self.RELLENO)
        assert "¿En qué medida el modelo mejora la precisión?" in texto

    def test_quita_instrucciones(self):
        texto, n = limpiar_texto("Sub Línea de Investigación:\nRedactar la sublínea según corresponda")
        assert n == 1 and "Redactar" not in texto

    def test_palabras_propias_descarta_encabezados_de_plantilla(self):
        assert palabras_propias("1.3. Importancia del estudio\n7\n1.4. Justificación del estudio") == 0
        assert palabras_propias("1.3. Importancia del estudio\nEl estudio beneficia a las MYPE") == 6


class TestPlantillaDocumento:
    def test_relleno_partido_por_salto_de_pagina(self):
        from ingest.plantilla import limpiar_paginas

        paginas = [
            "3.2. De acuerdo con la técnica de contrastación\nEl texto expositivo es aquel texto que "
            "ofrece al lector una información\nexplícita sobre un tema puntual, de manera objetiva, es decir, sin que\n4",
            "medie en ningún momento la opinión del autor o sus posicionamientos.\n4. Línea de investigación",
        ]
        limpias, n = limpiar_paginas(paginas)
        assert n == 1 and len(limpias) == 2
        assert "expositivo" not in limpias[0] and "medie" not in limpias[1]
        assert "Línea de investigación" in limpias[1]
