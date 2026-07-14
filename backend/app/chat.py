"""Chat post-evaluación acotado: contexto = JSON de la evaluación + rúbrica.

Mismas prohibiciones del juez: nunca reescribir ni mejorar el texto del
estudiante; si lo piden, el prompt instruye responder que este sistema solo
evalúa.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from graph.llm import Invocador, UsoLLM
from graph.prompts import _render, cargar_prompt
from rubrics.models import Rubrica

_MAX_CHARS_INFORME = 60_000


class RespuestaChat(BaseModel):
    respuesta: str


def invocador_por_defecto() -> Invocador:
    """Invocador real (modelo del juez 1). Los tests lo monkeypatchean."""
    from app.config import get_settings
    from graph.llm import crear_invocador

    return crear_invocador(get_settings().judge1_model)


def _resumen_rubrica(rubrica: Rubrica) -> str:
    lineas = [f"{rubrica.nombre} ({rubrica.id}); máximo {rubrica.puntaje_maximo:g} puntos."]
    for seccion in rubrica.secciones:
        lineas.append(f"- {seccion.id} {seccion.nombre} (máx {seccion.puntaje_max:g})")
    return "\n".join(lineas)


def _informe_compacto(resultado: dict) -> str:
    # El informe completo, sin el texto del reporte de indexación (ruido para el chat)
    compacto = dict(resultado)
    compacto.pop("reporte_indexacion", None)
    texto = json.dumps(compacto, ensure_ascii=False)
    return texto[:_MAX_CHARS_INFORME]


def responder_pregunta(
    resultado: dict, rubrica: Rubrica, pregunta: str, invocador: Invocador
) -> tuple[str, UsoLLM]:
    prompt = _render(
        cargar_prompt("chat_informe.md"),
        {
            "rubrica_resumen": _resumen_rubrica(rubrica),
            "informe_json": _informe_compacto(resultado),
            "pregunta": pregunta.strip(),
        },
    )
    parsed, uso = invocador(prompt, RespuestaChat)
    return parsed.respuesta, uso
