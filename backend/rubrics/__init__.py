"""Carga de rúbricas versionadas (JSON) del ECM."""

from __future__ import annotations

from pathlib import Path

from rubrics.models import Rubrica

RUBRICS_DIR = Path(__file__).resolve().parent


def rubricas_disponibles() -> list[str]:
    return sorted(p.stem for p in RUBRICS_DIR.glob("*_v*.json"))


def load_rubric(rubric_id: str) -> Rubrica:
    """Carga una rúbrica versionada por id (p. ej. 'especifica_v1')."""
    ruta = RUBRICS_DIR / f"{rubric_id}.json"
    if not ruta.exists():
        disponibles = ", ".join(rubricas_disponibles()) or "ninguna"
        raise FileNotFoundError(
            f"Rúbrica {rubric_id!r} no encontrada en {RUBRICS_DIR}. "
            f"Disponibles: {disponibles}. Genera los JSON con: python -m cli.build_rubrics"
        )
    return Rubrica.model_validate_json(ruta.read_text(encoding="utf-8"))
