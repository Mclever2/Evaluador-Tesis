"""Validación psicométrica del ECM contra jurados humanos.

Uso (desde backend/):
  python -m cli.validate --sistema ..\\data\\results --jurados ..\\gold\\jurados.csv
        [--rubrica ficha_upao_v1] [--salida ..\\data\\validation]

Entradas:
- Carpeta con resultados JSON del sistema (modo concordancia: ficha_upao_v1,
  escala 0-3 por ítem). El project_id de cada JSON debe coincidir con el
  proyecto_id del CSV de jurados (en batch_eval es el nombre del archivo).
- gold/jurados.csv con columnas: proyecto_id, jurado_id, item_id, puntaje
  (enteros 0 a 3). Un proyecto puede tener 2 o 3 jurados.

Salidas en data/validation/: reporte.md + CSVs con las tablas.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.config import ROOT
from metrics.psychometrics import (
    acuerdo_adyacente,
    acuerdo_exacto,
    bootstrap_ic,
    correlaciones,
    icc21,
    interpretar_kappa,
    mae,
    qwk,
)

ETIQUETAS_0_3 = [0, 1, 2, 3]
_ORDINAL_3N = {"no_cumple": 0, "parcial": 1, "cumple": 2}


# ── Carga de datos ───────────────────────────────────────────────────────────


def cargar_sistema(carpeta: Path, rubrica_id: str) -> dict[str, dict[str, int]]:
    """proyecto → {item_id → puntaje 0-3} desde los JSON del sistema."""
    sistema: dict[str, dict[str, int]] = {}
    for ruta in sorted(carpeta.glob("*.json")):
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        if datos.get("rubric_id") != rubrica_id:
            continue
        items: dict[str, int] = {}
        for seccion in datos.get("secciones", []):
            for item in seccion.get("items", []):
                nivel = item.get("nivel_final")
                if isinstance(nivel, int):
                    items[str(item["id"])] = nivel
        if items:
            sistema[str(datos["project_id"])] = items
    return sistema


def cargar_jurados(ruta: Path) -> dict[str, dict[str, dict[str, int]]]:
    """proyecto → {jurado → {item_id → puntaje}}."""
    jurados: dict[str, dict[str, dict[str, int]]] = {}
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        for fila in csv.DictReader(archivo):
            proyecto = str(fila["proyecto_id"]).strip()
            jurado = str(fila["jurado_id"]).strip()
            item = str(fila["item_id"]).strip()
            puntaje = int(fila["puntaje"])
            jurados.setdefault(proyecto, {}).setdefault(jurado, {})[item] = puntaje
    return jurados


def mediana_jurados(por_jurado: dict[str, dict[str, int]]) -> dict[str, int]:
    """Mediana por ítem entre jurados (mediana inferior con cantidad par)."""
    items: dict[str, list[int]] = {}
    for calificaciones in por_jurado.values():
        for item, puntaje in calificaciones.items():
            items.setdefault(item, []).append(puntaje)
    return {
        item: sorted(valores)[(len(valores) - 1) // 2] for item, valores in items.items()
    }


def _pares_alineados(
    a: dict[str, int], b: dict[str, int]
) -> tuple[list[int], list[int]]:
    comunes = sorted(set(a) & set(b))
    return [a[i] for i in comunes], [b[i] for i in comunes]


# ── Cálculos ─────────────────────────────────────────────────────────────────


def linea_base_humana(jurados: dict[str, dict[str, dict[str, int]]]) -> dict:
    """QWK por pares de jurados: ítems (global y por proyecto) y totales."""
    pares_items: dict[str, tuple[list[int], list[int]]] = {}
    por_proyecto: list[dict] = []
    totales: dict[str, dict[str, float]] = {}

    for proyecto, por_jurado in sorted(jurados.items()):
        nombres = sorted(por_jurado)
        for i, j1 in enumerate(nombres):
            totales.setdefault(j1, {})[proyecto] = float(sum(por_jurado[j1].values()))
            for j2 in nombres[i + 1 :]:
                a, b = _pares_alineados(por_jurado[j1], por_jurado[j2])
                clave = f"{j1}|{j2}"
                acumulado = pares_items.setdefault(clave, ([], []))
                acumulado[0].extend(a)
                acumulado[1].extend(b)
                por_proyecto.append(
                    {"proyecto": proyecto, "par": clave, "qwk_items": qwk(a, b, ETIQUETAS_0_3)}
                )

    qwk_global = {
        par: qwk(a, b, ETIQUETAS_0_3) for par, (a, b) in sorted(pares_items.items())
    }
    qwk_totales: dict[str, float] = {}
    for par in qwk_global:
        j1, j2 = par.split("|")
        proyectos = sorted(set(totales.get(j1, {})) & set(totales.get(j2, {})))
        if len(proyectos) >= 2:
            qwk_totales[par] = qwk(
                [round(totales[j1][p]) for p in proyectos],
                [round(totales[j2][p]) for p in proyectos],
                etiquetas=sorted(
                    {round(totales[j][p]) for j in (j1, j2) for p in proyectos}
                ),
            )
    return {
        "qwk_items_global": qwk_global,
        "qwk_items_promedio": float(np.mean(list(qwk_global.values()))) if qwk_global else float("nan"),
        "qwk_items_por_proyecto": por_proyecto,
        "qwk_totales": qwk_totales,
        "totales_por_jurado": totales,
    }


def sistema_contra_humanos(
    sistema: dict[str, dict[str, int]],
    jurados: dict[str, dict[str, dict[str, int]]],
    n_bootstrap: int = 2000,
) -> dict:
    proyectos = sorted(set(sistema) & set(jurados))
    if not proyectos:
        raise ValueError(
            "Ningún proyecto coincide entre el sistema y los jurados: verifica que "
            "project_id (nombre de archivo en batch_eval) == proyecto_id del CSV."
        )

    nombres_jurados = sorted({j for p in proyectos for j in jurados[p]})
    medianas = {p: mediana_jurados(jurados[p]) for p in proyectos}

    def series_item(raters_b: dict[str, dict[str, int]]) -> tuple[list[int], list[int]]:
        a_todo: list[int] = []
        b_todo: list[int] = []
        for p in proyectos:
            if p not in raters_b:
                continue
            a, b = _pares_alineados(sistema[p], raters_b[p])
            a_todo.extend(a)
            b_todo.extend(b)
        return a_todo, b_todo

    # Contra cada jurado
    contra_jurados = {}
    for jurado in nombres_jurados:
        raters_b = {p: jurados[p][jurado] for p in proyectos if jurado in jurados[p]}
        a, b = series_item(raters_b)
        contra_jurados[jurado] = {
            "qwk_items": qwk(a, b, ETIQUETAS_0_3),
            "acuerdo_exacto": acuerdo_exacto(a, b),
            "acuerdo_adyacente": acuerdo_adyacente(a, b),
            "n_items": len(a),
        }

    # Contra la mediana de jurados
    a_med, b_med = series_item(medianas)
    totales_sistema = {p: float(sum(sistema[p].values())) for p in proyectos}
    totales_mediana = {
        p: float(statistics.median([sum(c.values()) for c in jurados[p].values()]))
        for p in proyectos
    }
    lista_sistema = [totales_sistema[p] for p in proyectos]
    lista_mediana = [totales_mediana[p] for p in proyectos]

    def qwk_en_muestra(muestra: list[str]) -> float:
        a: list[int] = []
        b: list[int] = []
        for p in muestra:
            pa, pb = _pares_alineados(sistema[p], medianas[p])
            a.extend(pa)
            b.extend(pb)
        return qwk(a, b, ETIQUETAS_0_3)

    def mae_en_muestra(muestra: list[str]) -> float:
        return mae([totales_sistema[p] for p in muestra], [totales_mediana[p] for p in muestra])

    ic_qwk = bootstrap_ic(proyectos, qwk_en_muestra, n=n_bootstrap)
    ic_mae = bootstrap_ic(proyectos, mae_en_muestra, n=n_bootstrap)

    return {
        "proyectos": proyectos,
        "contra_jurados": contra_jurados,
        "contra_mediana": {
            "qwk_items": qwk(a_med, b_med, ETIQUETAS_0_3),
            "qwk_items_ic95": ic_qwk,
            "acuerdo_exacto": acuerdo_exacto(a_med, b_med),
            "acuerdo_adyacente": acuerdo_adyacente(a_med, b_med),
            "qwk_totales": qwk(
                [round(t) for t in lista_sistema],
                [round(t) for t in lista_mediana],
                etiquetas=sorted({round(t) for t in lista_sistema + lista_mediana}),
            ),
            "mae_totales": mae(lista_sistema, lista_mediana),
            "mae_ic95": ic_mae,
            "correlaciones": correlaciones(lista_sistema, lista_mediana),
            "icc21": icc21({"sistema": totales_sistema, "mediana_jurados": totales_mediana}),
            "n_items": len(a_med),
        },
        "totales_sistema": totales_sistema,
        "totales_mediana": totales_mediana,
    }


def acuerdo_interno_panel(carpeta: Path, rubrica_id: str) -> dict[str, float]:
    """QWK promedio entre los jueces del propio panel, a nivel ítem.

    Se alinea por pares: cada par de jueces se compara sobre los ítems que
    AMBOS calificaron (robusto ante huecos de API de un juez).
    """
    items_panel: list[dict[str, int]] = []
    for ruta in sorted(carpeta.glob("*.json")):
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        if datos.get("rubric_id") != rubrica_id:
            continue
        for seccion in datos.get("secciones", []):
            for item in seccion.get("items", []):
                niveles = item.get("niveles_jueces") or {}
                convertidos: dict[str, int] = {}
                for juez, nivel in niveles.items():
                    if isinstance(nivel, int):
                        convertidos[juez] = nivel
                    elif nivel in _ORDINAL_3N:
                        convertidos[juez] = _ORDINAL_3N[nivel]
                if len(convertidos) >= 2:
                    items_panel.append(convertidos)

    jueces = sorted({j for item in items_panel for j in item})
    resultado: dict[str, float] = {}
    valores: list[float] = []
    for i, j1 in enumerate(jueces):
        for j2 in jueces[i + 1 :]:
            a = [item[j1] for item in items_panel if j1 in item and j2 in item]
            b = [item[j2] for item in items_panel if j1 in item and j2 in item]
            if a:
                valor = qwk(a, b)
                resultado[f"{j1}|{j2}"] = valor
                valores.append(valor)
    resultado["promedio"] = float(np.mean(valores)) if valores else float("nan")
    return resultado


# ── Reporte ──────────────────────────────────────────────────────────────────


def _f(valor: float, decimales: int = 3) -> str:
    return "NA" if valor is None or (isinstance(valor, float) and np.isnan(valor)) else f"{valor:.{decimales}f}"


def generar_reporte(
    carpeta_sistema: Path,
    ruta_jurados: Path,
    salida: Path,
    rubrica_id: str = "ficha_upao_v1",
    n_bootstrap: int = 2000,
) -> Path:
    sistema = cargar_sistema(carpeta_sistema, rubrica_id)
    if not sistema:
        raise ValueError(
            f"No hay resultados del sistema con rúbrica {rubrica_id!r} en {carpeta_sistema}. "
            "El modo concordancia usa la ficha institucional (escala 0-3)."
        )
    jurados = cargar_jurados(ruta_jurados)
    base = linea_base_humana(jurados)
    contra = sistema_contra_humanos(sistema, jurados, n_bootstrap=n_bootstrap)
    panel = acuerdo_interno_panel(carpeta_sistema, rubrica_id)

    salida.mkdir(parents=True, exist_ok=True)

    # CSVs
    with (salida / "qwk_pares_jurados.csv").open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo, lineterminator="\n")
        escritor.writerow(["par", "qwk_items_global", "interpretacion", "qwk_totales"])
        for par, valor in base["qwk_items_global"].items():
            escritor.writerow(
                [par, _f(valor), interpretar_kappa(valor), _f(base["qwk_totales"].get(par, float("nan")))]
            )
    with (salida / "sistema_vs_jurados.csv").open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo, lineterminator="\n")
        escritor.writerow(["jurado", "qwk_items", "interpretacion", "acuerdo_exacto", "acuerdo_adyacente", "n_items"])
        for jurado, metricas in contra["contra_jurados"].items():
            escritor.writerow(
                [jurado, _f(metricas["qwk_items"]), interpretar_kappa(metricas["qwk_items"]),
                 _f(metricas["acuerdo_exacto"]), _f(metricas["acuerdo_adyacente"]), metricas["n_items"]]
            )
    with (salida / "totales.csv").open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.writer(archivo, lineterminator="\n")
        escritor.writerow(["proyecto_id", "total_sistema", "total_mediana_jurados"])
        for proyecto in contra["proyectos"]:
            escritor.writerow(
                [proyecto, contra["totales_sistema"][proyecto], contra["totales_mediana"][proyecto]]
            )

    # Markdown
    med = contra["contra_mediana"]
    lineas = [
        "# Validación psicométrica del ECM",
        "",
        f"Fecha: {datetime.now(timezone.utc).isoformat()}  ",
        f"Rúbrica: {rubrica_id} · proyectos emparejados: {len(contra['proyectos'])} · "
        f"bootstrap: {n_bootstrap} remuestreos sobre proyectos (IC 95%)",
        "",
        "## 1. Línea base humano-humano (QWK entre pares de jurados)",
        "",
        "| Par de jurados | QWK ítems (global) | Interpretación | QWK totales |",
        "| --- | --- | --- | --- |",
    ]
    for par, valor in base["qwk_items_global"].items():
        lineas.append(
            f"| {par} | {_f(valor)} | {interpretar_kappa(valor)} | "
            f"{_f(base['qwk_totales'].get(par, float('nan')))} |"
        )
    lineas += [
        "",
        f"Promedio de pares (ítems): **{_f(base['qwk_items_promedio'])}** "
        f"({interpretar_kappa(base['qwk_items_promedio'])})",
        "",
        "## 2. Sistema contra humanos",
        "",
        "| Comparación | QWK ítems | Interpretación | Acuerdo exacto | Acuerdo adyacente |",
        "| --- | --- | --- | --- | --- |",
    ]
    for jurado, metricas in contra["contra_jurados"].items():
        lineas.append(
            f"| sistema vs {jurado} | {_f(metricas['qwk_items'])} | "
            f"{interpretar_kappa(metricas['qwk_items'])} | {_f(metricas['acuerdo_exacto'])} | "
            f"{_f(metricas['acuerdo_adyacente'])} |"
        )
    lineas += [
        f"| sistema vs mediana de jurados | {_f(med['qwk_items'])} | "
        f"{interpretar_kappa(med['qwk_items'])} | {_f(med['acuerdo_exacto'])} | "
        f"{_f(med['acuerdo_adyacente'])} |",
        "",
        f"- QWK ítems (sistema vs mediana): **{_f(med['qwk_items'])}** "
        f"IC95% [{_f(med['qwk_items_ic95'][0])}, {_f(med['qwk_items_ic95'][1])}]",
        f"- QWK totales: {_f(med['qwk_totales'])}",
        f"- MAE de totales: **{_f(med['mae_totales'], 2)}** puntos "
        f"IC95% [{_f(med['mae_ic95'][0], 2)}, {_f(med['mae_ic95'][1], 2)}]",
        f"- Pearson: {_f(med['correlaciones']['pearson'])} · "
        f"Spearman: {_f(med['correlaciones']['spearman'])}",
        f"- ICC(2,1) de totales (sistema, mediana): {_f(med['icc21'])}",
        "",
        "## 3. Acuerdo interno del panel de jueces LLM",
        "",
    ]
    for par, valor in panel.items():
        if par != "promedio":
            lineas.append(f"- {par}: {_f(valor)} ({interpretar_kappa(valor)})")
    lineas += [
        f"- **Promedio del panel: {_f(panel.get('promedio', float('nan')))}** "
        f"({interpretar_kappa(panel.get('promedio', float('nan')))})",
        "",
        "Interpretación de QWK según Landis y Koch (1977): 0.00-0.20 leve, "
        "0.21-0.40 aceptable, 0.41-0.60 moderado, 0.61-0.80 sustancial, "
        "0.81-1.00 casi perfecto.",
    ]
    ruta_reporte = salida / "reporte.md"
    ruta_reporte.write_text("\n".join(lineas), encoding="utf-8")
    return ruta_reporte


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validacion psicometrica del ECM")
    parser.add_argument("--sistema", default=str(ROOT / "data" / "results"))
    parser.add_argument("--jurados", default=str(ROOT / "gold" / "jurados.csv"))
    parser.add_argument("--rubrica", default="ficha_upao_v1")
    parser.add_argument("--salida", default=str(ROOT / "data" / "validation"))
    parser.add_argument("--bootstrap", type=int, default=2000)
    args = parser.parse_args(argv)

    ruta = generar_reporte(
        Path(args.sistema), Path(args.jurados), Path(args.salida),
        rubrica_id=args.rubrica, n_bootstrap=args.bootstrap,
    )
    print(f"Reporte generado: {ruta}")
    print(f"CSVs en: {Path(args.salida)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
