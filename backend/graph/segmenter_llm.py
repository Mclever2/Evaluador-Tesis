"""Respaldo LLM del segmentador estructural.

Solo se invoca cuando la heurística de encabezados encuentra menos secciones
que el umbral. Envía al LLM las líneas candidatas (índice, página, texto) y
recibe, por sección de la rúbrica, el índice de línea donde comienza.
"""

from __future__ import annotations

from typing import Callable, Optional

from graph.llm import Invocador, UsoLLM
from graph.prompts import render_prompt_segmentador
from graph.schemas import RespuestaSegmentacionLLM
from graph.segmenter import (
    ResultadoSegmentacion,
    SeccionSegmentada,
    _es_pagina_indice,
    _MIN_PALABRAS_SECCION,
)
from ingest.extractors import DocumentoExtraido
from rubrics.models import Rubrica

_MAX_LINEAS_CANDIDATAS = 400
_MAX_CHARS_LINEA = 100


def crear_fallback_llm(
    invocador: Invocador,
    on_uso: Optional[Callable[[UsoLLM], None]] = None,
) -> Callable[[DocumentoExtraido, Rubrica], ResultadoSegmentacion]:
    def fallback(doc: DocumentoExtraido, rubrica: Rubrica) -> ResultadoSegmentacion:
        paginas_indice = [p.numero for p in doc.paginas if _es_pagina_indice(p.texto)]

        lineas: list[tuple[int, int, str]] = []  # (indice global, pagina, texto)
        indice = 0
        for pagina in doc.paginas:
            for texto in pagina.texto.splitlines():
                lineas.append((indice, pagina.numero, texto))
                indice += 1

        candidatas = [
            (i, pag, texto.strip())
            for i, pag, texto in lineas
            if texto.strip()
            and len(texto.strip()) <= _MAX_CHARS_LINEA
            and sum(c.isalpha() for c in texto) >= 4
            and pag not in paginas_indice
        ][:_MAX_LINEAS_CANDIDATAS]

        prompt = render_prompt_segmentador(
            rubrica, [f"{i} | pág. {pag} | {texto}" for i, pag, texto in candidatas]
        )
        parsed, uso = invocador(prompt, RespuestaSegmentacionLLM)
        if on_uso:
            on_uso(uso)

        indices_validos = {i for i, _, _ in candidatas}
        asignaciones = {
            a.seccion_id: a.indice_linea
            for a in parsed.asignaciones
            if a.indice_linea is not None and a.indice_linea in indices_validos
        }
        cortes = sorted(asignaciones.values())

        advertencias = ["Segmentación realizada por respaldo LLM (la heurística no fue suficiente)."]
        secciones: list[SeccionSegmentada] = []
        for seccion in rubrica.secciones:
            inicio = asignaciones.get(seccion.id)
            if inicio is None:
                secciones.append(
                    SeccionSegmentada(seccion_id=seccion.id, nombre=seccion.nombre, presente=False)
                )
                continue
            siguientes = [c for c in cortes if c > inicio]
            fin = siguientes[0] if siguientes else len(lineas)
            cuerpo = lineas[inicio + 1 : fin]
            texto = "\n".join(t for _, _, t in cuerpo).strip()
            palabras = len(texto.split())
            secciones.append(
                SeccionSegmentada(
                    seccion_id=seccion.id,
                    nombre=seccion.nombre,
                    presente=True,
                    encontrado_como=lineas[inicio][2].strip(),
                    pagina_inicio=lineas[inicio][1],
                    pagina_fin=cuerpo[-1][1] if cuerpo else lineas[inicio][1],
                    palabras=palabras,
                    texto=texto,
                )
            )
            if palabras < _MIN_PALABRAS_SECCION:
                advertencias.append(
                    f"{seccion.id} ({seccion.nombre}): solo {palabras} palabras; "
                    "posiblemente aún no redactada."
                )

        return ResultadoSegmentacion(
            secciones=secciones,
            advertencias=advertencias,
            paginas_indice=paginas_indice,
            metodo="llm",
        )

    return fallback
