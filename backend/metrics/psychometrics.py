"""Métricas psicométricas para la VALIDACIÓN del instrumento (no por proyecto).

Se usan desde cli/validate.py y cli/retest.py para comparar al sistema contra
jurados humanos sobre un conjunto de proyectos: QWK, acuerdo exacto y
adyacente, MAE, correlaciones, ICC(2,1) e intervalos bootstrap. Nada de esto
va en la interfaz ni se calcula por proyecto individual.
"""

from __future__ import annotations

import random
from typing import Callable, Optional, Sequence

import numpy as np


def qwk(a: Sequence[int], b: Sequence[int], etiquetas: Optional[Sequence[int]] = None) -> float:
    """Kappa ponderado cuadrático de Cohen (sklearn, weights='quadratic')."""
    from sklearn.metrics import cohen_kappa_score

    etiquetas = list(etiquetas) if etiquetas is not None else sorted(set(a) | set(b))
    if len(etiquetas) < 2:
        return 1.0 if list(a) == list(b) else 0.0
    return float(cohen_kappa_score(list(a), list(b), weights="quadratic", labels=etiquetas))


def acuerdo_exacto(a: Sequence[int], b: Sequence[int]) -> float:
    """Proporción de coincidencias exactas (0-1)."""
    pares = list(zip(a, b))
    return sum(1 for x, y in pares if x == y) / len(pares) if pares else 0.0


def acuerdo_adyacente(a: Sequence[int], b: Sequence[int], tolerancia: int = 1) -> float:
    """Proporción con diferencia <= tolerancia niveles (0-1)."""
    pares = list(zip(a, b))
    return sum(1 for x, y in pares if abs(x - y) <= tolerancia) / len(pares) if pares else 0.0


def mae(a: Sequence[float], b: Sequence[float]) -> float:
    pares = list(zip(a, b))
    return sum(abs(x - y) for x, y in pares) / len(pares) if pares else 0.0


def correlaciones(a: Sequence[float], b: Sequence[float]) -> dict[str, float]:
    from scipy.stats import pearsonr, spearmanr

    if len(a) < 3:
        return {"pearson": float("nan"), "spearman": float("nan")}
    return {
        "pearson": float(pearsonr(list(a), list(b))[0]),
        "spearman": float(spearmanr(list(a), list(b))[0]),
    }


def icc21(totales_por_rater: dict[str, dict[str, float]]) -> float:
    """ICC(2,1) con pingouin. Entrada: rater → {proyecto → total}.

    Solo considera proyectos calificados por TODOS los raters.
    """
    import pandas as pd
    import pingouin as pg

    raters = list(totales_por_rater)
    proyectos = set.intersection(*(set(v) for v in totales_por_rater.values()))
    filas = [
        {"proyecto": p, "rater": r, "total": totales_por_rater[r][p]}
        for r in raters
        for p in sorted(proyectos)
    ]
    if len(proyectos) < 3:
        return float("nan")
    df = pd.DataFrame(filas)
    tabla = pg.intraclass_corr(data=df, targets="proyecto", raters="rater", ratings="total")
    # ICC(2,1) de Shrout-Fleiss = dos vías aleatorias, acuerdo absoluto, medida
    # única. Pingouin lo etiqueta "ICC2" (versiones antiguas) o "ICC(A,1)".
    fila = tabla[tabla["Type"].isin(["ICC2", "ICC(A,1)"])]
    if fila.empty:
        return float("nan")
    return float(fila["ICC"].iloc[0])


def interpretar_kappa(valor: float) -> str:
    """Bandas de Landis y Koch (1977)."""
    if np.isnan(valor):
        return "no calculable"
    if valor < 0:
        return "pobre (peor que el azar)"
    if valor <= 0.20:
        return "leve"
    if valor <= 0.40:
        return "aceptable"
    if valor <= 0.60:
        return "moderado"
    if valor <= 0.80:
        return "sustancial"
    return "casi perfecto"


def bootstrap_ic(
    proyectos: Sequence[str],
    estadistico: Callable[[Sequence[str]], float],
    n: int = 2000,
    seed: int = 42,
    confianza: float = 0.95,
) -> tuple[float, float]:
    """IC percentil por bootstrap REMUESTREANDO PROYECTOS (no ítems)."""
    rng = random.Random(seed)
    proyectos = list(proyectos)
    valores = []
    for _ in range(n):
        muestra = [proyectos[rng.randrange(len(proyectos))] for _ in proyectos]
        try:
            valor = estadistico(muestra)
        except Exception:
            continue
        if not np.isnan(valor):
            valores.append(valor)
    if not valores:
        return (float("nan"), float("nan"))
    alfa = (1 - confianza) / 2
    return (
        float(np.percentile(valores, alfa * 100)),
        float(np.percentile(valores, (1 - alfa) * 100)),
    )


def kappa_promedio_pares(
    puntajes_por_rater: dict[str, list[int]], etiquetas: Optional[Sequence[int]] = None
) -> dict[str, float]:
    """QWK por cada par de raters (listas alineadas) y su promedio."""
    raters = sorted(puntajes_por_rater)
    resultado: dict[str, float] = {}
    valores = []
    for i, r1 in enumerate(raters):
        for r2 in raters[i + 1 :]:
            valor = qwk(puntajes_por_rater[r1], puntajes_por_rater[r2], etiquetas)
            resultado[f"{r1}|{r2}"] = valor
            valores.append(valor)
    resultado["promedio"] = float(np.mean(valores)) if valores else float("nan")
    return resultado
