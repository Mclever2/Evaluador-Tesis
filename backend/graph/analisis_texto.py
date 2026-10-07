"""Utilidades de texto deterministas para los análisis de coherencia (Toulmin y coherencia global).

Son reglas fijas, sin LLM: texto propio del estudiante (sin la plantilla), normalización para comparar
citas, elegibilidad de una sección argumentativa y verificación de que una cita exista en el texto.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from ingest.plantilla import lineas_plantilla, normalizar_linea

VINETA = re.compile(r"^\s*(?:[-•●▪◦*]|\d{1,2}[.)])\s+")

# Sección argumentativa completa (no apuntes): 80+ palabras propias y 60 %+ de ellas en oraciones completas.
MIN_PALABRAS = 80
MIN_PROPORCION_ORACIONES = 0.6
MIN_PALABRAS_ORACION = 8


def texto_propio(texto: str) -> str:
    """Texto de la sección sin las líneas de la plantilla UPAO ni los números de página."""
    firma = lineas_plantilla()
    lineas = [l for l in texto.splitlines()
              if normalizar_linea(l) and normalizar_linea(l) not in firma
              and not re.fullmatch(r"[\d\s.\-–]+", normalizar_linea(l))]
    return re.sub(r"[ \t]+", " ", "\n".join(lineas)).strip()


def elegibilidad(texto: str) -> dict:
    """Una sección es elegible si está redactada en prosa y no en apuntes.

    Oración completa: termina en . ? ! y tiene 8+ palabras, aunque esté redactada como viñeta.
    """
    palabras = len(texto.split())
    unido = " ".join(VINETA.sub("", l).strip() for l in texto.splitlines())
    oraciones = [o.strip() for o in re.split(r"(?<=[.?!])\s+", unido) if o.strip()]
    en_oraciones = sum(len(o.split()) for o in oraciones
                       if o[-1] in ".?!" and len(o.split()) >= MIN_PALABRAS_ORACION)
    proporcion = en_oraciones / palabras if palabras else 0.0
    return {"palabras": palabras, "proporcion_oraciones": round(proporcion, 3),
            "elegible": palabras >= MIN_PALABRAS and proporcion >= MIN_PROPORCION_ORACIONES}


def normalizar(t: str) -> str:
    # algunos modelos devuelven tildes mal escapadas: "investigaci\x00f3n" en vez de "investigación"
    t = re.sub("\x00([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), t)
    t = unicodedata.normalize("NFKC", t).lower()
    t = re.sub(r"-\s*\n\s*", "", t)  # palabras partidas al final de línea en el PDF
    t = re.sub(r"[\"“”'‘’«»]", "", t)
    return re.sub(r"\s+", " ", t).strip(" .;:,")


def palabras(t: str) -> list[str]:
    return re.findall(r"\w+", normalizar(t))


def cita_en_texto(cita: str, palabras_texto: list[str], umbral: float = 0.85) -> bool:
    """La cita existe si el 85 %+ de sus palabras aparecen en una ventana contigua del texto.

    Tolera los cortes de línea y guiones del PDF, la puntuación y pequeñas omisiones del modelo, pero
    rechaza citas inventadas o parafraseadas.
    """
    q = palabras(cita)
    if not q:
        return False
    n = len(q)
    objetivo = Counter(q)
    for i in range(0, max(1, len(palabras_texto) - n + 1)):
        ventana = Counter(palabras_texto[i:i + n + 2])
        if sum(min(c, ventana[w]) for w, c in objetivo.items()) / n >= umbral:
            return True
    return False
