"""Carga y renderizado de los prompts versionados (backend/prompts/*.md).

El renderizado usa reemplazo literal de marcadores {nombre} (no str.format),
para que las llaves del texto del estudiante no rompan la plantilla. El hash
SHA-256 del conjunto de prompts se registra en cada resultado (trazabilidad).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from rubrics.models import Rubrica, SeccionRubrica

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

_ARCHIVOS_PROMPTS = ["juez_base.md", "juez_roles.md", "transversales.md", "segmentador.md"]


def cargar_prompt(nombre: str) -> str:
    return (PROMPTS_DIR / nombre).read_text(encoding="utf-8")


def hash_prompts() -> str:
    sha = hashlib.sha256()
    for nombre in _ARCHIVOS_PROMPTS:
        ruta = PROMPTS_DIR / nombre
        if ruta.exists():
            sha.update(nombre.encode())
            sha.update(ruta.read_bytes())
    return sha.hexdigest()[:16]


def _render(plantilla: str, valores: dict[str, str]) -> str:
    for clave, valor in valores.items():
        plantilla = plantilla.replace("{" + clave + "}", valor)
    return plantilla


def roles_jueces() -> dict[int, str]:
    """Extrae los bloques '## juezN' de juez_roles.md."""
    texto = cargar_prompt("juez_roles.md")
    roles: dict[int, str] = {}
    for m in re.finditer(r"^## juez(\d)\s*\n(.*?)(?=^## juez\d|\Z)", texto, re.MULTILINE | re.DOTALL):
        roles[int(m.group(1))] = m.group(2).strip()
    if set(roles) != {1, 2, 3}:
        raise ValueError("juez_roles.md debe definir exactamente los bloques juez1, juez2 y juez3")
    return roles


def _texto_escala(rubrica: Rubrica) -> str:
    if rubrica.tipo == "ponderada_3_niveles":
        return (
            "- cumple: todos los componentes que el criterio exige están presentes y "
            "correctos en el texto (deficiencias = \"ninguna\").\n"
            "- parcial: hay deficiencias reales y demostrables en algún componente "
            "exigido: incompleto, impreciso o con errores menores.\n"
            "- no_cumple: un componente esencial del criterio está ausente, es "
            "incorrecto, o queda contradicho por otra sección del proyecto.\n"
            "El nivel se DERIVA de las deficiencias anotadas: ni bajar el nivel sin "
            "deficiencia citable, ni dar cumple con deficiencias sustantivas anotadas."
        )
    return (
        "Asigna un entero de 0 a 3 por criterio:\n"
        "- 3 (Excelente): todos los componentes exigidos presentes y correctos "
        "(deficiencias = \"ninguna\").\n"
        "- 2 (Bueno): deficiencias reales pero menores en componentes secundarios.\n"
        "- 1 (Regular): deficiencias importantes; el criterio se satisface a medias.\n"
        "- 0 (Insuficiente): componente esencial ausente, incorrecto o contradicho.\n"
        "El nivel se DERIVA de las deficiencias anotadas: ni bajar el nivel sin "
        "deficiencia citable, ni dar nota alta con deficiencias sustantivas anotadas."
    )


def _texto_items(seccion: SeccionRubrica) -> str:
    lineas = []
    for item in seccion.items:
        ref = f" (Ref: {item.referencia})" if item.referencia else ""
        lineas.append(f"- [{item.id}] {item.criterio}{ref}")
    return "\n".join(lineas)


def _texto_contexto(pasajes: list[str]) -> str:
    if not pasajes:
        return ""
    cuerpo = "\n".join(f"- {p}" for p in pasajes)
    return (
        "# Contexto normativo de apoyo\n\n"
        "Pasajes de literatura metodológica recuperados para esta sección. Úsalos SOLO "
        "para fundamentar la redacción de tus observaciones; NO cambian los criterios, "
        "los niveles ni tu decisión.\n\n" + cuerpo
    )


def _texto_trazabilidad(contexto: str) -> str:
    if not contexto:
        return ""
    return (
        "# Contexto de trazabilidad (extractos de otras secciones del mismo proyecto)\n\n"
        "Úsalo para dos cosas: (1) los criterios que exigen correspondencia entre "
        "secciones (título, problema, objetivos, hipótesis, diseño, muestra); (2) "
        "detectar CONTRADICCIONES internas: si estos extractos contradicen lo que la "
        "sección evaluada afirma (p. ej. declara asignación aleatoria pero la muestra "
        "se selecciona por accesibilidad, o las limitaciones admiten grupos intactos), "
        "el criterio afectado no puede ser cumple. No califiques la calidad de estos "
        "extractos en sí mismos.\n\n"
        f"<<<\n{contexto}\n>>>"
    )


def render_prompt_juez(
    rol_enfoque: str,
    rubrica: Rubrica,
    seccion: SeccionRubrica,
    texto_seccion: str,
    pasajes_rag: list[str] | None = None,
    contexto_trazabilidad: str = "",
) -> str:
    return _render(
        cargar_prompt("juez_base.md"),
        {
            "rol_enfoque": rol_enfoque,
            "seccion_nombre": seccion.nombre,
            "escala": _texto_escala(rubrica),
            "items": _texto_items(seccion),
            "contexto_normativo": _texto_contexto(pasajes_rag or []),
            "contexto_trazabilidad": _texto_trazabilidad(contexto_trazabilidad),
            "dato_palabras": str(len(texto_seccion.split())),
            "texto_seccion": texto_seccion,
        },
    )


def render_prompt_transversales(rol_enfoque: str, texto_proyecto: str) -> str:
    return _render(
        cargar_prompt("transversales.md"),
        {"rol_enfoque": rol_enfoque, "texto_proyecto": texto_proyecto},
    )


def render_prompt_segmentador(rubrica: Rubrica, lineas: list[str]) -> str:
    secciones = "\n".join(f"- {s.id}: {s.nombre}" for s in rubrica.secciones)
    return _render(
        cargar_prompt("segmentador.md"),
        {"secciones": secciones, "lineas": "\n".join(lineas)},
    )
