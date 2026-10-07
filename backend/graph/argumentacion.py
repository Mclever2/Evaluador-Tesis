"""Índice argumentativo según el modelo de Toulmin (versión 1.1): coherencia DENTRO de las secciones.

Externo a la rúbrica: no modifica ni recalcula sus puntajes. Analiza las secciones argumentativas
COMPLETAS: S02, descripción y delimitación del problema, y S05, justificación. El marco teórico es
expositivo y no se analiza.

Procedimiento:
  1. ELEGIBILIDAD (regla fija): 80+ palabras propias y 60 %+ de ellas en oraciones completas.
  2. SEGMENTACIÓN (regla fija): la sección se divide en oraciones numeradas; los rótulos van aparte.
  3. FUNCIÓN DE CADA ORACIÓN (un LLM, temperatura 0, semilla fija): afirmación, dato, garantía,
     respaldo, refutación o ninguno, según prompts/argumentacion_toulmin.md. El modelo no copia texto.
  4. CALIFICADOR (regla fija): diccionario de atenuadores en las oraciones del autor (afirmación o garantía).
  5. PUNTAJE (regla fija): índice estructural = tipos de componente presentes / 6 (Qin y Karabacak, 2010);
     nivel 0-5 adaptado de Erduran, Simon y Osborne (2004), solo descriptivo.
"""

from __future__ import annotations

import re
import statistics as st

from graph.analisis_texto import VINETA, elegibilidad, texto_propio
from graph.llm import Invocador, UsoLLM
from graph.prompts import cargar_prompt, render
from graph.schemas import (
    EtiquetaOracion,
    OracionArgumentativa,
    RespuestaArgumentacion,
    ResultadoArgumentacion,
    SeccionArgumentativa,
)
from graph.segmenter import ResultadoSegmentacion

VERSION = "1.1"
SECCIONES = {"S02": "Descripción y delimitación del problema", "S05": "Justificación, importancia y viabilidad"}
FUNCIONES = ["afirmacion", "dato", "garantia", "respaldo", "refutacion", "ninguno"]
COMPONENTES = ["afirmacion", "dato", "garantia", "respaldo", "calificador", "refutacion"]

# Expresiones atenuadoras (hedges). No incluye "puede"/"pueden" solos (suelen expresar capacidad) ni
# "prácticamente" con el sentido de "en la práctica".
CALIFICADORES = [
    r"probablemente", r"posiblemente", r"presumiblemente", r"aparentemente", r"al parecer", r"quiz[aá]s?",
    r"tal vez", r"podr[ií]a(n)?", r"pudiera(n)?", r"puede(n)? que", r"es posible que", r"es probable que",
    r"suele(n)?", r"tiende(n)? a", r"en general", r"generalmente", r"por lo general", r"habitualmente",
    r"frecuentemente", r"a menudo", r"en la mayor[ií]a de", r"en gran medida", r"en cierta medida",
    r"en parte", r"solo en parte", r"parcialmente", r"relativamente", r"en principio",
    r"parece(n)? que", r"sugiere(n)? que", r"se estima que",
    r"pr[aá]cticamente (nul[oa]s?|inexistentes?|ningun[oa]?s?|imposibles?|todos?|todas?|iguales?|ausentes?)",
]
PATRON_CALIFICADOR = re.compile(r"\b(" + "|".join(CALIFICADORES) + r")\b", re.IGNORECASE)

ABREVIATURAS = ["et al.", "p. ej.", "etc.", "Sr.", "Sra.", "Dr.", "Dra.", "Fig.", "N°.", "núm.", "pp.", "p.",
                "vol.", "ed.", "eds.", "aprox.", "e.g.", "i.e.", "op. cit.", "cap.", "art."]
CORTE, MARCA = " ", "⁣"
INICIO = re.compile(r"^[A-ZÁÉÍÓÚÑ¿¡\d]")


def es_rotulo(linea: str, anterior: str | None, siguiente: str | None) -> bool:
    """Título o subtítulo, distinto de una línea partida del PDF: corto, sin puntuación final, con
    mayúscula inicial, tras una línea que cierra oración y antes de una que empieza con mayúscula."""
    return (len(linea.split()) <= 8 and not re.search(r"[.,;?!]$", linea) and bool(INICIO.match(linea))
            and (anterior is None or bool(re.search(r"[.?!:]$", anterior)))
            and (siguiente is None or bool(INICIO.match(siguiente))))


def oraciones(texto: str) -> list[str]:
    crudas = [l.strip() for l in texto.splitlines() if l.strip()]
    limpias = [VINETA.sub("", l) for l in crudas]
    piezas = []
    for i, (crudo, l) in enumerate(zip(crudas, limpias)):
        if not l:
            continue
        anterior = limpias[i - 1] if i > 0 else None
        siguiente = limpias[i + 1] if i + 1 < len(limpias) else None
        if es_rotulo(l, anterior, siguiente):
            piezas.append(f"{CORTE}{l}{CORTE}")
        else:
            piezas.append(CORTE + l if VINETA.match(crudo) else l)
    unido = " ".join(piezas)
    for a in ABREVIATURAS:
        unido = re.sub(re.escape(a), a.replace(".", MARCA), unido, flags=re.IGNORECASE)
    partes: list[str] = []
    for bloque in unido.split(CORTE):
        partes += re.split(r"(?<=[.?!])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\"“(\d])", bloque)
    salida = [re.sub(r"\s+", " ", p.replace(MARCA, ".")).strip() for p in partes]
    return [o for o in salida if len(o.split()) >= 4]


def calificadores_en(oracion: str) -> list[str]:
    return [m.group(0) for m in PATRON_CALIFICADOR.finditer(oracion)]


def puntuar(etiquetas: list[EtiquetaOracion], ors: list[str]) -> dict:
    validas = {e.id: e for e in etiquetas if 1 <= e.id <= len(ors)}
    funciones = {e.funcion for e in validas.values()}
    calif = {i: calificadores_en(ors[i - 1]) for i, e in validas.items() if e.funcion in ("afirmacion", "garantia")}
    calif = {i: c for i, c in calif.items() if c}
    refut = [e for e in validas.values() if e.funcion == "refutacion"]
    respondidas = [e for e in refut if e.responde_en and e.responde_en != e.id and e.responde_en in validas]
    presentes = [c for c in COMPONENTES if (c == "calificador" and calif) or c in funciones]
    fundamentos = bool(funciones & {"dato", "garantia", "respaldo"})
    nivel = (0 if "afirmacion" not in funciones else 1 if not fundamentos else 2 if not refut
             else 3 if not respondidas else 4 if len(respondidas) == 1 else 5)
    return {"conteo": {f: sum(e.funcion == f for e in validas.values()) for f in FUNCIONES},
            "oraciones_con_calificador": len(calif), "refutaciones_respondidas": len(respondidas),
            "presentes": presentes, "indice_estructural": round(len(presentes) / 6, 3), "nivel": nivel,
            "calificadores": calif, "validas": validas}


def analizar_argumentacion(segmentacion: ResultadoSegmentacion, invocador: Invocador,
                           modelo: str) -> tuple[ResultadoArgumentacion, list[UsoLLM]]:
    presentes = {s.seccion_id: s for s in segmentacion.presentes}
    secciones, usos = [], []
    for sid, nombre in SECCIONES.items():
        texto = texto_propio(presentes[sid].texto) if sid in presentes else ""
        eleg = elegibilidad(texto)
        sec = SeccionArgumentativa(seccion_id=sid, nombre=nombre, elegible=eleg["elegible"],
                                   palabras=eleg["palabras"], proporcion_oraciones=eleg["proporcion_oraciones"])
        if eleg["elegible"]:
            ors = oraciones(texto)
            numeradas = "\n".join(f"[{i}] {o}" for i, o in enumerate(ors, start=1))
            prompt = render(cargar_prompt("argumentacion_toulmin.md"),
                            {"seccion": nombre, "oraciones": numeradas, "n": str(len(ors))})
            respuesta, uso = invocador(prompt, RespuestaArgumentacion)
            usos.append(uso)
            p = puntuar(respuesta.etiquetas, ors)
            sec.oraciones = len(ors)
            sec.conteo = p["conteo"]
            sec.oraciones_con_calificador = p["oraciones_con_calificador"]
            sec.refutaciones_respondidas = p["refutaciones_respondidas"]
            sec.presentes = p["presentes"]
            sec.indice_estructural = p["indice_estructural"]
            sec.nivel = p["nivel"]
            sec.detalle = [OracionArgumentativa(
                id=i, oracion=o,
                funcion=p["validas"][i].funcion if i in p["validas"] else "sin_etiqueta",
                responde_en=p["validas"][i].responde_en if i in p["validas"] else None,
                calificadores=p["calificadores"].get(i, [])) for i, o in enumerate(ors, start=1)]
        secciones.append(sec)
    indices = [s.indice_estructural for s in secciones if s.indice_estructural is not None]
    return ResultadoArgumentacion(version=VERSION, modelo=modelo, secciones=secciones,
                                  indice_proyecto=round(st.mean(indices), 3) if indices else None), usos

