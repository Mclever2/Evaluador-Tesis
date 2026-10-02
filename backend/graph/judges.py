"""Jueces del panel: una llamada LLM por par (juez, sección) que califica
TODOS los ítems de esa sección en un solo JSON. Con 15 secciones y 3 jueces
son como máximo 45 llamadas por proyecto, más 3 de dimensiones transversales.

Si un juez falla de forma persistente en una sección (tras los reintentos con
backoff del invocador), se registra el hueco y el agregador trabaja con los
jueces disponibles marcando panel_incompleto.
"""

from __future__ import annotations

from typing import Callable, Optional

from pydantic import BaseModel

from graph.llm import Invocador
from graph.prompts import render_prompt_juez, render_prompt_transversales, roles_jueces
from graph.schemas import (
    RespuestaSeccionDicotomica,
    RespuestaSeccionEscala,
    RespuestaSeccionPonderada,
    RespuestaTransversales,
    ResultadoJuez,
)
from graph.segmenter import MIN_PALABRAS_EVALUABLES, ResultadoSegmentacion
from rubrics.models import Rubrica

# Máximo de caracteres por sección al armar el extracto del proyecto para las
# dimensiones transversales (las secciones clave de trazabilidad van completas).
_SECCIONES_CLAVE_TRANSVERSALES = {"S01", "S03", "S04", "S08", "S12"}
_TRUNCADO_TRANSVERSALES = 1500

# Secciones cuyo texto alimenta el bloque de trazabilidad de TODOS los jueces:
# correspondencia entre secciones Y detección de contradicciones internas
# (diseño vs muestreo vs limitaciones). Se eligen por nombre normalizado para
# funcionar con cualquier rúbrica.
_CLAVES_TRAZABILIDAD = (
    "titulo", "formulacion", "objetivo", "hipotesis", "planteamiento",
    "diseno", "tipo y metodo", "poblacion", "muestra", "limitacion",
)
_TRUNCADO_TRAZABILIDAD = 1200

# seccion_id → pasajes normativos de apoyo (RAG opcional)
ContextoRag = Callable[[str], list[str]]


class ConfigJuez(BaseModel):
    numero: int
    modelo: str
    rol_enfoque: str


def construir_configuracion_panel(modelos: dict[int, str]) -> list[ConfigJuez]:
    roles = roles_jueces()
    return [
        ConfigJuez(numero=n, modelo=modelos[n], rol_enfoque=roles[n]) for n in sorted(modelos)
    ]


def _texto_para_transversales(segmentacion: ResultadoSegmentacion) -> str:
    partes: list[str] = []
    for seccion in segmentacion.presentes:
        texto = seccion.texto
        if seccion.seccion_id not in _SECCIONES_CLAVE_TRANSVERSALES:
            texto = texto[:_TRUNCADO_TRANSVERSALES]
        partes.append(f"[{seccion.seccion_id} {seccion.nombre}]\n{texto}")
    return "\n\n".join(partes)


def _texto_trazabilidad(rubrica: Rubrica, segmentacion: ResultadoSegmentacion) -> str:
    """Extractos de título/problema/objetivos/hipótesis para los criterios de
    correspondencia entre secciones (los jueces solo ven su propia sección)."""
    from rubrics.parser import normalizar

    partes: list[str] = []
    for seccion in segmentacion.presentes:
        rubro = next((s for s in rubrica.secciones if s.id == seccion.seccion_id), None)
        if rubro is None or not seccion.texto:
            continue
        nombre_norm = normalizar(rubro.nombre)
        if any(clave in nombre_norm for clave in _CLAVES_TRAZABILIDAD):
            partes.append(
                f"[{rubro.nombre}]\n{seccion.texto[:_TRUNCADO_TRAZABILIDAD]}"
            )
    return "\n\n".join(partes)


def evaluar_con_juez(
    cfg: ConfigJuez,
    invocador: Invocador,
    rubrica: Rubrica,
    segmentacion: ResultadoSegmentacion,
    secciones_activas: set[str],
    contexto_rag: Optional[ContextoRag] = None,
    on_progreso: Optional[Callable[[dict], None]] = None,
) -> ResultadoJuez:
    """Ejecuta el lote completo de un juez: secciones activas presentes + transversales."""
    schema = {
        "ponderada_3_niveles": RespuestaSeccionPonderada,
        "dicotomica": RespuestaSeccionDicotomica,
    }.get(rubrica.tipo, RespuestaSeccionEscala)
    resultado = ResultadoJuez(juez=cfg.numero, modelo=cfg.modelo)

    presentes = {s.seccion_id: s for s in segmentacion.presentes}
    trazabilidad = _texto_trazabilidad(rubrica, segmentacion)
    for seccion in rubrica.secciones:
        if seccion.id not in secciones_activas or seccion.id not in presentes:
            continue  # ausentes y no activas: sin llamada (el agregador las resuelve)
        if presentes[seccion.id].palabras_evaluables < MIN_PALABRAS_EVALUABLES:
            continue  # sin contenido evaluable: no se gasta llamada (agregador puntúa 0)
        pasajes = contexto_rag(seccion.id) if contexto_rag else []
        prompt = render_prompt_juez(
            cfg.rol_enfoque, rubrica, seccion, presentes[seccion.id].texto, pasajes,
            contexto_trazabilidad=trazabilidad,
        )
        try:
            parsed, uso = invocador(prompt, schema)
            resultado.secciones[seccion.id] = parsed
            resultado.tokens_entrada += uso.tokens_entrada
            resultado.tokens_salida += uso.tokens_salida
        except Exception as exc:  # falla persistente tras reintentos → hueco
            resultado.secciones[seccion.id] = None
            resultado.huecos.append(f"{seccion.id}: {exc}")
        if on_progreso:
            on_progreso(
                {"tipo": "juez_seccion", "juez": cfg.numero, "seccion": seccion.id,
                 "ok": resultado.secciones[seccion.id] is not None}
            )

    prompt_trans = render_prompt_transversales(
        cfg.rol_enfoque, _texto_para_transversales(segmentacion)
    )
    try:
        parsed, uso = invocador(prompt_trans, RespuestaTransversales)
        resultado.transversales = parsed
        resultado.tokens_entrada += uso.tokens_entrada
        resultado.tokens_salida += uso.tokens_salida
    except Exception as exc:
        resultado.huecos.append(f"transversales: {exc}")
    if on_progreso:
        on_progreso({"tipo": "juez_transversales", "juez": cfg.numero,
                     "ok": resultado.transversales is not None})
    return resultado
