"""Ingesta de libros de metodología (PDF) a la biblioteca RAG opcional.

Uso (desde backend/):
  python -m cli.ingest_library ruta\al\libro.pdf [otro.pdf ...]
  python -m cli.ingest_library --listar
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from library.store import ingestar_pdf, libros_ingresados


def main() -> int:
    parser = argparse.ArgumentParser(description="Biblioteca metodologica del ECM")
    parser.add_argument("pdfs", nargs="*", help="PDFs de libros de metodologia")
    parser.add_argument("--listar", action="store_true", help="Lista los libros ingresados")
    args = parser.parse_args()

    if args.listar or not args.pdfs:
        libros = libros_ingresados()
        if not libros:
            print("Biblioteca vacia. El sistema evalua igual sin RAG.")
        for libro in libros:
            print(f"  {libro['libro']}: {libro['fragmentos']} fragmentos")
        return 0

    for ruta in args.pdfs:
        ruta = Path(ruta)
        if not ruta.exists():
            print(f"[!] No existe: {ruta}")
            continue
        print(f"Ingresando {ruta.name} (esto genera embeddings locales)...")
        fragmentos = ingestar_pdf(ruta)
        print(f"[OK] {ruta.name}: {fragmentos} fragmentos indexados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
