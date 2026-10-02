"""Genera los JSON versionados de rúbricas a partir de las fuentes en docs/.

Uso (desde backend/):  python -m cli.build_rubrics

- docs/rubrica_especifica.md → backend/rubrics/especifica_v1.json
- docs/ficha_upao.md → backend/rubrics/ficha_upao_v1.json (cuando exista)

Imprime un resumen de validación y las advertencias del parser. No corrige la
fuente: cualquier inconsistencia debe resolverla el autor del instrumento.
"""

from __future__ import annotations

import sys
from pathlib import Path

from rubrics import RUBRICS_DIR
from rubrics.parser import FICHA_PENDIENTE_MSG, parse_dicotomica, parse_especifica, parse_ficha_upao

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


def main() -> int:
    fuente = DOCS / "rubrica_especifica.md"
    if not fuente.exists():
        print(f"ERROR: no existe {fuente}. Coloca la rúbrica fuente en docs/.")
        return 1

    rubrica, advertencias = parse_especifica(fuente.read_text(encoding="utf-8"))
    destino = RUBRICS_DIR / f"{rubrica.id}.json"
    destino.write_text(rubrica.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")

    # Salida solo ASCII: la consola de Windows usa cp1252 por defecto.
    print(f"[OK] {rubrica.id}: {len(rubrica.secciones)} secciones, "
          f"{rubrica.total_items} items, maximo {rubrica.puntaje_maximo:g} pts")
    print(f"     -> {destino}")
    for seccion in rubrica.secciones:
        marca = "" if seccion.suma_pesos() == round(seccion.puntaje_max, 2) else "  [!] pesos != maximo"
        print(f"    {seccion.id}  max {seccion.puntaje_max:>4g}  "
              f"items {len(seccion.items):>2}  suma pesos {seccion.suma_pesos():>5g}{marca}")

    if advertencias:
        print("\nAdvertencias del parser (la fuente manda; no se corrigio nada):")
        for adv in advertencias:
            print(f"  [!] {adv.encode('ascii', 'replace').decode()}")

    dicotomica = DOCS / "rubrica_dicotomica_v2.md"
    if dicotomica.exists():
        rub_d, adv_d = parse_dicotomica(dicotomica.read_text(encoding="utf-8"))
        destino_d = RUBRICS_DIR / f"{rub_d.id}.json"
        destino_d.write_text(rub_d.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        print(f"\n[OK] {rub_d.id}: {len(rub_d.secciones)} dimensiones, {rub_d.total_items} items, "
              f"maximo {rub_d.puntaje_maximo:g} pts (dicotomica)")
        print(f"     -> {destino_d}")
        for adv in adv_d:
            print(f"  [!] {adv.encode('ascii', 'replace').decode()}")

    ficha = DOCS / "ficha_upao.md"
    if not ficha.exists():
        print("\n[i] ficha_upao_v1 omitida: "
              + FICHA_PENDIENTE_MSG.encode("ascii", "replace").decode())
        return 0

    rubrica_ficha, advertencias_ficha = parse_ficha_upao(ficha.read_text(encoding="utf-8"))
    destino_ficha = RUBRICS_DIR / f"{rubrica_ficha.id}.json"
    destino_ficha.write_text(
        rubrica_ficha.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
    )
    print(f"\n[OK] {rubrica_ficha.id}: {len(rubrica_ficha.secciones)} bloques, "
          f"{rubrica_ficha.total_items} items, maximo {rubrica_ficha.puntaje_maximo:g} pts, "
          f"conversion vigesimal con {len(rubrica_ficha.conversion_vigesimal or [])} bandas "
          f"(87 -> nota {rubrica_ficha.nota_vigesimal(87)})")
    print(f"     -> {destino_ficha}")
    for seccion in rubrica_ficha.secciones:
        print(f"    {seccion.id}  max {seccion.puntaje_max:>4g}  items {len(seccion.items):>2}")
    if advertencias_ficha:
        print("\nAdvertencias del parser de la ficha:")
        for adv in advertencias_ficha:
            print(f"  [!] {adv.encode('ascii', 'replace').decode()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
