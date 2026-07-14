"""Estabilidad test-retest del sistema: k corridas del mismo conjunto.

Uso (desde backend/):
  python -m cli.retest carpeta\\con\\proyectos [--k 3] [--rubrica especifica_v1]
        [--modo completo] [--salida ..\\data\\validation]

Evalúa k veces cada proyecto con la MISMA configuración y reporta la
estabilidad entre corridas: QWK a nivel ítem por par de corridas, ICC(2,1) de
totales entre corridas y porcentaje de ítems idénticos. Con temperature 0 y
seed fija se espera variación mínima; este subcomando la CUANTIFICA.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from anonymizer.anonymizer import anonimizar
from app import runner
from app.config import ROOT
from graph.evaluation_graph import ConfigEvaluacion
from ingest.extractors import extraer_documento
from metrics.psychometrics import acuerdo_exacto, icc21, interpretar_kappa, qwk

_ORDINAL_3N = {"no_cumple": 0, "parcial": 1, "cumple": 2}


def _puntajes_item(resultado) -> dict[str, int]:
    puntajes: dict[str, int] = {}
    for seccion in resultado.secciones:
        for item in seccion.items:
            nivel = item.nivel_final
            if isinstance(nivel, int):
                puntajes[f"{seccion.id}.{item.id}"] = nivel
            elif nivel in _ORDINAL_3N:
                puntajes[f"{seccion.id}.{item.id}"] = _ORDINAL_3N[nivel]
    return puntajes


def ejecutar_retest(
    carpeta: Path,
    k: int = 3,
    rubrica: str = "especifica_v1",
    modo: str = "completo",
) -> dict:
    archivos = sorted([*carpeta.glob("*.pdf"), *carpeta.glob("*.docx")], key=lambda p: p.name.lower())
    if not archivos:
        raise ValueError(f"No hay proyectos en {carpeta}")

    # corrida → proyecto → (items, total)
    corridas: list[dict[str, tuple[dict[str, int], float]]] = []
    for numero in range(1, k + 1):
        print(f"Corrida {numero}/{k}")
        datos: dict[str, tuple[dict[str, int], float]] = {}
        for archivo in archivos:
            doc = extraer_documento(archivo)
            doc_anonimo, reporte_anon, _ = anonimizar(doc)
            panel = runner.crear_panel(lambda e: None)
            resultado = panel.evaluar(
                doc_anonimo,
                reporte_anon,
                ConfigEvaluacion(project_id=archivo.stem, rubric_id=rubrica, mode=modo),
            )
            datos[archivo.stem] = (_puntajes_item(resultado), resultado.total)
            print(f"  {archivo.stem}: total {resultado.total:g}")
        corridas.append(datos)

    proyectos = sorted(set.intersection(*(set(c) for c in corridas)))
    qwk_pares: dict[str, float] = {}
    identicos: dict[str, float] = {}
    for i in range(k):
        for j in range(i + 1, k):
            a_serie: list[int] = []
            b_serie: list[int] = []
            for proyecto in proyectos:
                items_a, _ = corridas[i][proyecto]
                items_b, _ = corridas[j][proyecto]
                comunes = sorted(set(items_a) & set(items_b))
                a_serie.extend(items_a[m] for m in comunes)
                b_serie.extend(items_b[m] for m in comunes)
            clave = f"corrida{i + 1}|corrida{j + 1}"
            qwk_pares[clave] = qwk(a_serie, b_serie)
            identicos[clave] = acuerdo_exacto(a_serie, b_serie)

    icc = icc21(
        {
            f"corrida{i + 1}": {p: corridas[i][p][1] for p in proyectos}
            for i in range(k)
        }
    )
    totales_por_proyecto = {
        p: [corridas[i][p][1] for i in range(k)] for p in proyectos
    }
    return {
        "k": k,
        "proyectos": proyectos,
        "qwk_pares": qwk_pares,
        "qwk_promedio": float(np.mean(list(qwk_pares.values()))) if qwk_pares else float("nan"),
        "identicos": identicos,
        "identicos_promedio": float(np.mean(list(identicos.values()))) if identicos else float("nan"),
        "icc21_totales": icc,
        "totales": totales_por_proyecto,
    }


def escribir_reporte(resumen: dict, salida: Path, rubrica: str) -> Path:
    salida.mkdir(parents=True, exist_ok=True)
    with (salida / "retest_totales.csv").open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo, lineterminator="\n")
        escritor.writerow(["proyecto_id"] + [f"total_corrida{i + 1}" for i in range(resumen["k"])]
                          + ["desviacion_estandar"])
        for proyecto, totales in resumen["totales"].items():
            desviacion = statistics.pstdev(totales) if len(totales) > 1 else 0.0
            escritor.writerow([proyecto] + totales + [round(desviacion, 3)])

    lineas = [
        "# Estabilidad test-retest del ECM",
        "",
        f"Fecha: {datetime.now(timezone.utc).isoformat()}  ",
        f"Rúbrica: {rubrica} · k = {resumen['k']} corridas · {len(resumen['proyectos'])} proyectos",
        "",
        "| Par de corridas | QWK ítems | Interpretación | % ítems idénticos |",
        "| --- | --- | --- | --- |",
    ]
    for par, valor in resumen["qwk_pares"].items():
        lineas.append(
            f"| {par} | {valor:.3f} | {interpretar_kappa(valor)} | "
            f"{resumen['identicos'][par] * 100:.1f}% |"
        )
    icc = resumen["icc21_totales"]
    lineas += [
        "",
        f"- QWK promedio entre corridas: **{resumen['qwk_promedio']:.3f}**",
        f"- Ítems idénticos (promedio): **{resumen['identicos_promedio'] * 100:.1f}%**",
        f"- ICC(2,1) de totales entre corridas: **{'NA' if np.isnan(icc) else f'{icc:.3f}'}**",
        "",
        "Con temperature 0, top_p 1 y seed fija se espera QWK cercano a 1 y "
        "variación mínima de totales; los valores de esta tabla cuantifican la "
        "estabilidad real del instrumento.",
    ]
    ruta = salida / "retest.md"
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    return ruta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test-retest del ECM")
    parser.add_argument("carpeta")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--rubrica", default="especifica_v1")
    parser.add_argument("--modo", default="completo", choices=["completo", "progresivo"])
    parser.add_argument("--salida", default=str(ROOT / "data" / "validation"))
    args = parser.parse_args(argv)

    resumen = ejecutar_retest(Path(args.carpeta), k=args.k, rubrica=args.rubrica, modo=args.modo)
    ruta = escribir_reporte(resumen, Path(args.salida), args.rubrica)
    print(f"Reporte test-retest: {ruta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
