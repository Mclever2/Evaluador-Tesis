"""Evaluación por lotes: una carpeta completa de proyectos → CSV consolidado.

Uso (desde backend/):
  python -m cli.batch_eval carpeta\con\pdfs [--rubrica especifica_v1] [--modo completo]
        [--semanas 1 2 3] [--sin-administrativos] [--salida ..\data\results\consolidado.csv]

El project_id de cada resultado es el NOMBRE DEL ARCHIVO sin extensión: usa los
mismos nombres en gold/jurados.csv para el CLI de validación.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from anonymizer.anonymizer import anonimizar
from app import runner, storage
from graph.evaluation_graph import ConfigEvaluacion
from ingest.extractors import extraer_documento


def _ascii(texto: str) -> str:
    return str(texto).encode("ascii", "replace").decode()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluacion por lotes del ECM")
    parser.add_argument("carpeta", help="Carpeta con proyectos .pdf/.docx")
    parser.add_argument("--rubrica", default="especifica_v1")
    parser.add_argument("--modo", default="completo", choices=["completo", "progresivo"])
    parser.add_argument("--semanas", type=int, nargs="*", default=None)
    parser.add_argument("--sin-administrativos", action="store_true")
    parser.add_argument("--salida", default=None, help="Ruta del CSV consolidado")
    args = parser.parse_args(argv)

    carpeta = Path(args.carpeta)
    archivos = sorted(
        [*carpeta.glob("*.pdf"), *carpeta.glob("*.docx")], key=lambda p: p.name.lower()
    )
    if not archivos:
        print(f"No hay .pdf ni .docx en {carpeta}")
        return 1

    salida = Path(args.salida) if args.salida else storage.results_dir() / "consolidado.csv"
    print(f"{len(archivos)} proyectos | rubrica {args.rubrica} | modo {args.modo}")

    filas: list[dict] = []
    errores: list[str] = []
    inicio_lote = time.time()
    for i, archivo in enumerate(archivos, start=1):
        print(f"\n[{i}/{len(archivos)}] {_ascii(archivo.name)}")
        try:
            doc = extraer_documento(archivo)
            doc_anonimo, reporte_anon, mapeo = anonimizar(doc)

            panel = runner.crear_panel(
                lambda e: e.get("tipo") == "fase" and print(f"    - {_ascii(e.get('detalle', ''))}")
            )
            config = ConfigEvaluacion(
                project_id=archivo.stem,
                rubric_id=args.rubrica,
                mode=args.modo,
                semanas_activas=args.semanas,
                incluir_administrativos=not args.sin_administrativos,
            )
            resultado = panel.evaluar(doc_anonimo, reporte_anon, config)

            # Persistencia igual que la API: JSON en data/results + indice SQLite
            reporte = resultado.reporte_indexacion
            storage_id = storage.guardar_proyecto(doc_anonimo, reporte, mapeo)
            evaluation_id = storage.crear_evaluacion(storage_id, args.rubrica, args.modo)
            import json as _json

            storage.guardar_resultado(
                evaluation_id, _json.loads(resultado.model_dump_json(exclude_none=False))
            )

            from app.exporters import fila_consolidada

            filas.append(fila_consolidada(_json.loads(resultado.model_dump_json())))
            print(
                f"    OK total {resultado.total:g}/{resultado.puntaje_max_activo:g} "
                f"({_ascii(resultado.nivel or '')}) | discrepancia {resultado.panel.pct_discrepancia}% "
                f"| {resultado.costo.tokens_entrada + resultado.costo.tokens_salida} tokens"
            )
        except Exception as exc:  # noqa: BLE001 — un proyecto no tumba el lote
            errores.append(f"{archivo.name}: {exc}")
            print(f"    ERROR: {_ascii(exc)}")

    if filas:
        salida.parent.mkdir(parents=True, exist_ok=True)
        import csv as _csv
        import io as _io

        columnas: list[str] = []
        for fila in filas:
            for columna in fila:
                if columna not in columnas:
                    columnas.append(columna)
        buffer = _io.StringIO()
        escritor = _csv.DictWriter(buffer, fieldnames=columnas, lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(filas)
        salida.write_text(buffer.getvalue(), encoding="utf-8")
        print(f"\nCSV consolidado ({len(filas)} filas): {salida}")

    if errores:
        print(f"\n{len(errores)} proyectos con error:")
        for error in errores:
            print(f"  [!] {_ascii(error)}")
    print(f"Tiempo total: {time.time() - inicio_lote:.1f}s")
    return 0 if filas else 1


if __name__ == "__main__":
    sys.exit(main())
