"""Coherencia global del proyecto (versión 1.3): contradicciones verificadas y nota por regla fija.

Externa a la rúbrica: no modifica ni recalcula sus puntajes. Reemplaza la coherencia interna 1-5 que el
panel ponía como juicio global, que tenía bajo acuerdo entre jueces (CCI = 0.40).

Qué mide: si el proyecto COMPLETO sigue una sola línea argumental sin contradicciones entre sus partes.
Complementa a la trazabilidad (correspondencias puntuales de la rúbrica) y al índice argumentativo de
Toulmin (coherencia dentro de cada sección).

Procedimiento:
  1. TEXTO (regla fija): secciones con texto propio, sin la plantilla, anonimizadas, salvo el marco
     teórico (expositivo). Cada sección se recorta a 600 palabras.
  2. DETECCIÓN (un LLM, temperatura 0, semilla fija): lista las contradicciones entre dos partes, con la
     cita literal de cada una, según prompts/coherencia_global.md. No pone nota.
  3. VERIFICACIÓN (regla fija): una contradicción cuenta solo si ambas citas existen en el texto (85 %+ de
     sus palabras en una ventana contigua, para tolerar los cortes de línea del PDF).
  4. GRAVEDAD (regla fija, por tipo): del núcleo si afecta variables, unidad de análisis, propósito o
     diseño; menor en los demás casos.
  5. NOTA 1-5 (regla fija): 5 sin contradicciones · 4 una menor · 3 dos o más menores, o una del núcleo ·
     2 una del núcleo con dos o más menores, o dos del núcleo · 1 tres o más del núcleo.
"""

from __future__ import annotations

from typing import Optional

from graph.analisis_texto import cita_en_texto, normalizar, palabras, texto_propio
from graph.llm import Invocador, UsoLLM
from graph.prompts import cargar_prompt, render
from graph.schemas import ContradiccionVerificada, RespuestaCoherencia, ResultadoCoherenciaGlobal
from graph.segmenter import ResultadoSegmentacion

VERSION = "1.3"
EXCLUIDAS = {"S07"}  # marco teórico: expositivo
MAX_PALABRAS_SECCION = 600
TIPOS_NUCLEO = {"variables", "unidad_analisis", "proposito", "diseno"}


def texto_proyecto(segmentacion: ResultadoSegmentacion) -> tuple[str, str]:
    """Devuelve (texto para el prompt, texto completo para verificar las citas)."""
    partes, completo = [], []
    for s in segmentacion.presentes:
        if s.seccion_id in EXCLUIDAS:
            continue
        propio = texto_propio(s.texto)
        palabras_sec = propio.split()
        if len(palabras_sec) < 5:
            continue
        recorte = " ".join(palabras_sec[:MAX_PALABRAS_SECCION])
        if len(palabras_sec) > MAX_PALABRAS_SECCION:
            recorte += " [...]"
        partes.append(f"## {s.nombre}\n{recorte}")
        completo.append(propio)
    return "\n\n".join(partes), "\n".join(completo)


def nota_por_regla(nucleo: int, menor: int) -> int:
    if nucleo == 0:
        return 5 if menor == 0 else 4 if menor == 1 else 3
    if nucleo == 1:
        return 3 if menor <= 1 else 2
    return 2 if nucleo == 2 else 1


def verificar(respuesta: RespuestaCoherencia, texto_completo: str) -> tuple[list[ContradiccionVerificada], list[dict]]:
    palabras_texto = palabras(texto_completo)
    vistas, verificadas, rechazadas = set(), [], []
    for c in respuesta.contradicciones:
        a, b = normalizar(c.cita_a), normalizar(c.cita_b)
        motivo = ("cita de menos de 5 palabras" if len(a.split()) < 5 or len(b.split()) < 5 else
                  "cita no encontrada en el texto" if not cita_en_texto(a, palabras_texto)
                  or not cita_en_texto(b, palabras_texto) else
                  "ambas citas son iguales" if a == b else "")
        if motivo:
            rechazadas.append({**c.model_dump(), "motivo_rechazo": motivo})
            continue
        clave = (c.tipo, *sorted((a[:60], b[:60])))
        if clave in vistas:
            continue
        vistas.add(clave)
        verificadas.append(ContradiccionVerificada(
            **c.model_dump(), gravedad="nucleo" if c.tipo in TIPOS_NUCLEO else "menor"))
    return verificadas, rechazadas


def analizar_coherencia_global(segmentacion: ResultadoSegmentacion, invocador: Invocador,
                               modelo: str) -> tuple[Optional[ResultadoCoherenciaGlobal], list[UsoLLM]]:
    texto_prompt, completo = texto_proyecto(segmentacion)
    if not texto_prompt:  # sin texto del estudiante la coherencia no está definida (no es un 5)
        return None, []
    respuesta, uso = invocador(render(cargar_prompt("coherencia_global.md"), {"texto": texto_prompt}),
                               RespuestaCoherencia)
    verificadas, rechazadas = verificar(respuesta, completo)
    nucleo = sum(c.gravedad == "nucleo" for c in verificadas)
    menor = len(verificadas) - nucleo
    return ResultadoCoherenciaGlobal(
        version=VERSION, modelo=modelo, nota=nota_por_regla(nucleo, menor),
        contradicciones_nucleo=nucleo, contradicciones_menores=menor,
        propuestas=len(respuesta.contradicciones), contradicciones=verificadas, rechazadas=rechazadas,
    ), [uso]
