"""Inspecciona la ingesta de un proyecto sin evaluarlo.

Uso (desde backend/):  python -m cli.index_report ruta\al\proyecto.pdf [--rubrica especifica_v1]

Ejecuta el pipeline extracción → anonimización → segmentación y muestra el
reporte de indexación en consola (solo ASCII, por la consola de Windows).
"""

from __future__ import annotations

import argparse
import sys

from anonymizer.anonymizer import anonimizar
from graph.segmenter import segmentar
from ingest.extractors import extraer_documento
from rubrics import load_rubric


def _ascii(texto: str) -> str:
    return texto.encode("ascii", "replace").decode()


def main() -> int:
    parser = argparse.ArgumentParser(description="Reporte de indexacion del ECM")
    parser.add_argument("ruta", help="Proyecto de tesis (.pdf o .docx)")
    parser.add_argument("--rubrica", default="especifica_v1")
    args = parser.parse_args()

    rubrica = load_rubric(args.rubrica)
    doc = extraer_documento(args.ruta)
    doc_anonimo, reporte_anon, mapeo = anonimizar(doc)
    resultado = segmentar(doc_anonimo, rubrica)
    resultado.anonimizacion = reporte_anon

    print(f"Documento : {_ascii(doc.nombre)} ({doc.tipo}, {len(doc.paginas)} paginas"
          f"{'' if doc.paginacion_real else ' aprox.'}, {doc.total_palabras} palabras)")
    print(f"Rubrica   : {rubrica.id}")
    if resultado.paginas_indice:
        print(f"Indice    : paginas {resultado.paginas_indice} (omitidas al segmentar)")

    print("\nAnonimizacion (doble ciego):")
    if reporte_anon.reemplazos:
        for tipo, cantidad in sorted(reporte_anon.reemplazos.items()):
            print(f"  {tipo:<8} {cantidad} reemplazo(s)")
    else:
        print("  (no se enmascaro nada)")
    print(f"  mapeo local con {len(mapeo)} entradas (no se envia al LLM)")

    print("\nSecciones detectadas:")
    print(f"  {'ID':<5}{'Seccion':<48}{'Pags':<10}{'Palabras':>9}")
    for fila in resultado.reporte()["secciones"]:
        if fila["presente"]:
            pags = f"{fila['pagina_inicio']}-{fila['pagina_fin']}"
            print(f"  {fila['id']:<5}{_ascii(fila['nombre'])[:46]:<48}{pags:<10}{fila['palabras']:>9}")
        else:
            print(f"  {fila['id']:<5}{_ascii(fila['nombre'])[:46]:<48}{'NO ENCONTRADA':<10}")

    if resultado.advertencias or reporte_anon.advertencias:
        print("\nAdvertencias:")
        for adv in reporte_anon.advertencias + resultado.advertencias:
            print(f"  [!] {_ascii(adv)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
