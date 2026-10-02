"""Limpieza de la plantilla UPAO: separa el contenido del estudiante del relleno.

La plantilla oficial del curso trae texto de relleno en TODAS las secciones
("El texto expositivo es aquel texto que...") e instrucciones para el
estudiante ("Redactar la sublínea según corresponda"). Sin esta limpieza el
segmentador ve las 15 secciones "presentes" con cientos de palabras en un
proyecto sin avance, los jueces reciben relleno y pueden otorgar crédito por
rótulos que la plantilla ya trae escritos ("Aplicada", "Hg:", "H1:").

Dos operaciones, ambas deterministas:
- `limpiar_texto`: elimina las oraciones de relleno y las instrucciones
  literales de la plantilla (tolerante a saltos de línea y espacios).
- `palabras_propias`: cuenta las palabras de un texto descartando las líneas
  idénticas a líneas de la plantilla oficial (encabezados, esqueletos de
  tablas, ejemplos) y los números de página. Decide si una sección tiene
  contenido evaluable; no modifica el texto que ven los jueces.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_FIRMA = Path(__file__).resolve().parent / "plantilla_upao_lineas.txt"

# Oraciones de relleno de la plantilla, en el orden en que aparecen.
_RELLENO = [
    "El texto expositivo es aquel texto que ofrece al lector una información explícita "
    "sobre un tema puntual, de manera objetiva, es decir, sin que medie en ningún momento "
    "la opinión del autor o sus posicionamientos.",
    "En consecuencia, tampoco necesita utilizar argumentaciones para convencer.",
    "Textos expositivos divulgativos.",
    "Son aquellos que están dirigidos a un público amplio, sin requerimientos previos "
    "especializados, y, por lo tanto, abordan temas de interés general, usualmente desde "
    "una perspectiva relativamente simple.",
    "Sus oraciones tienden a ser breves y fáciles de comprender, y su lenguaje es llano y accesible.",
]

# Instrucciones literales de la plantilla dirigidas al estudiante.
_INSTRUCCIONES = [
    "Título del proyecto de tesis (Solo con mayúscula la primera letra y los nombres "
    "propios, máximo 20 palabras y sin comillas)",
    "(hasta la sgte semana)",
    "Redactar la línea o sublínea según corresponda",
    "Redactar la sublínea según corresponda",
    "Colocar la línea o sublínea (según corresponda).",
    "Elija un elemento.",
    "(con hipervínculo, luego borrar)",
    "(Sin grado académico, luego borrar)",
    "(la tabla es solo referencial)",
    "MARCAR MODALIDAD: P SP D",
]


# Fragmentos del relleno que quedan cuando el estudiante escribe en medio de la
# oración de la plantilla. Se aplican DESPUÉS de las oraciones completas.
_FRAGMENTOS = [
    "El texto expositivo es aquel texto que ofrece al lector una información",
]

# Entre palabras: espacios/saltos y, opcionalmente, un número de página
# intercalado por un salto de página (p. ej. "sin que / 4 / medie").
_SEP_PALABRAS = r"\s+(?:\d{1,3}\s+)?"

# Separador de páginas al limpiar el documento completo (form feed).
_SALTO_PAGINA = chr(12)


def _patron_flexible(frase: str) -> re.Pattern[str]:
    """Frase literal tolerante a saltos de línea, espacios y números de página."""
    palabras = [re.escape(p) for p in frase.split()]
    return re.compile(_SEP_PALABRAS.join(palabras), re.IGNORECASE)


_PATRONES = [_patron_flexible(f) for f in _RELLENO + _INSTRUCCIONES + _FRAGMENTOS]


def _reemplazo(m: re.Match[str]) -> str:
    # Conserva los separadores de página que el patrón haya cruzado.
    return " " + _SALTO_PAGINA * m.group(0).count(_SALTO_PAGINA)


def limpiar_texto(texto: str) -> tuple[str, int]:
    """Quita relleno e instrucciones de la plantilla. Devuelve (texto, n_eliminados)."""
    eliminados = 0
    for patron in _PATRONES:
        texto, n = patron.subn(_reemplazo, texto)
        eliminados += n
    # Las líneas que quedaron solo con espacios se vacían (conserva los saltos).
    # split por salto de línea y no splitlines(): splitlines también corta en form feed.
    lineas = texto.split(chr(10))
    texto = chr(10).join(l if l.strip(chr(32) + chr(9) + chr(13)) else "" for l in lineas)
    return texto, eliminados


def limpiar_paginas(paginas: list[str]) -> tuple[list[str], int]:
    """Limpia el documento completo: el relleno puede cruzar un salto de página."""
    texto, n = limpiar_texto(_SALTO_PAGINA.join(paginas))
    partes = texto.split(_SALTO_PAGINA)
    if len(partes) != len(paginas):  # salvaguarda: nunca desalinear la paginación
        return [limpiar_texto(p)[0] for p in paginas], n
    return partes, n


def normalizar_linea(linea: str) -> str:
    return re.sub(r"\s+", " ", linea).strip().lower()


@lru_cache
def lineas_plantilla() -> frozenset[str]:
    if not _FIRMA.exists():
        return frozenset()
    return frozenset(
        normalizar_linea(l) for l in _FIRMA.read_text(encoding="utf-8").splitlines() if l.strip()
    )


def palabras_propias(texto: str) -> int:
    """Palabras que no provienen de la plantilla (ni son números de página)."""
    firma = lineas_plantilla()
    total = 0
    for linea in texto.splitlines():
        norm = normalizar_linea(linea)
        if not norm or norm in firma or re.fullmatch(r"[\d\s.\-–]+", norm):
            continue
        total += len(norm.split())
    return total
