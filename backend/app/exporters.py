"""Exportación de resultados: CSV plano por proyecto y CSV consolidado.

El consolidado tiene UNA FILA POR PROYECTO con total, nivel, subtotales por
sección, dimensiones transversales, métricas determinísticas, índice argumentativo
(Toulmin), coherencia global y banderas de discrepancia — listo para SPSS o
Python (pandas.read_csv).
"""

from __future__ import annotations

import csv
import io


def csv_items(resultado: dict) -> str:
    """CSV plano de una evaluación: una fila por ítem."""
    salida = io.StringIO()
    escritor = csv.writer(salida, lineterminator="\n")
    escritor.writerow(
        ["project_id", "rubric_id", "mode", "seccion_id", "seccion", "item_id",
         "nivel_final", "puntaje", "puntaje_max", "discrepancia",
         "niveles_jueces", "evidencia", "observacion"]
    )
    for seccion in resultado.get("secciones", []):
        for item in seccion.get("items", []):
            niveles = item.get("niveles_jueces") or {}
            escritor.writerow(
                [
                    resultado.get("project_id"), resultado.get("rubric_id"),
                    resultado.get("mode"), seccion.get("id"), seccion.get("nombre"),
                    item.get("id"), item.get("nivel_final"), item.get("puntaje"),
                    item.get("puntaje_max"), int(bool(item.get("discrepancia"))),
                    "|".join(f"{k}={v}" for k, v in niveles.items()),
                    item.get("evidencia", ""), item.get("observacion", ""),
                ]
            )
    return salida.getvalue()


def _columna_transversal(resultado: dict, dimension: str):
    for t in resultado.get("dimensiones_transversales", []):
        if t.get("dimension") == dimension:
            return t.get("mediana")
    return None


def _columnas_coherencia(resultado: dict) -> dict:
    """Índice argumentativo (Toulmin) por sección y coherencia global; vacías si no se ejecutaron."""
    arg = resultado.get("argumentacion") or {}
    coh = resultado.get("coherencia_global") or {}
    secciones = {s.get("seccion_id"): s for s in arg.get("secciones", [])}
    columnas = {"toulmin_indice_proyecto": arg.get("indice_proyecto")}
    for sid in ("S02", "S05"):
        s = secciones.get(sid) or {}
        columnas[f"toulmin_indice_{sid}"] = s.get("indice_estructural")
        columnas[f"toulmin_nivel_{sid}"] = s.get("nivel")
    columnas.update({
        "coherencia_global": coh.get("nota"),
        "contradicciones_nucleo": coh.get("contradicciones_nucleo"),
        "contradicciones_menores": coh.get("contradicciones_menores"),
    })
    return columnas


def fila_consolidada(resultado: dict) -> dict:
    """Aplana una evaluación a la fila del consolidado."""
    metricas = resultado.get("metricas_deterministicas") or {}
    legibilidad = metricas.get("legibilidad") or {}
    lexico = metricas.get("riqueza_lexica") or {}
    citas = metricas.get("citas_referencias") or {}
    completitud = metricas.get("completitud") or {}
    panel = resultado.get("panel") or {}

    fila: dict = {
        "project_id": resultado.get("project_id"),
        "rubric_id": resultado.get("rubric_id"),
        "mode": resultado.get("mode"),
        "timestamp": resultado.get("timestamp"),
        "total": resultado.get("total"),
        "total_normalizado": resultado.get("total_normalizado"),
        "puntaje_max_activo": resultado.get("puntaje_max_activo"),
        "nivel": resultado.get("nivel"),
        "nota_vigesimal": resultado.get("nota_vigesimal"),
    }
    for seccion in resultado.get("secciones", []):
        fila[f"sub_{seccion['id']}"] = seccion.get("subtotal")
    fila.update(
        {
            "trans_coherencia_interna": _columna_transversal(resultado, "coherencia_interna"),
            "trans_formalidad_registro": _columna_transversal(resultado, "formalidad_registro"),
            "trans_claridad_tono": _columna_transversal(resultado, "claridad_tono"),
            "fernandez_huerta": legibilidad.get("fernandez_huerta"),
            "szigriszt_pazos": legibilidad.get("szigriszt_pazos"),
            "ttr": lexico.get("ttr"),
            "mtld": lexico.get("mtld"),
            "palabras_totales": metricas.get("palabras_totales"),
            "longitud_media_oracion": metricas.get("longitud_media_oracion"),
            "citas_en_texto": citas.get("citas_en_texto"),
            "referencias_en_lista": citas.get("referencias_en_lista"),
            "n_citas_sin_referencia": len(citas.get("citas_sin_referencia") or []),
            "n_referencias_nunca_citadas": len(citas.get("referencias_nunca_citadas") or []),
            "secciones_presentes": completitud.get("presentes"),
            "pct_discrepancia": panel.get("pct_discrepancia"),
            "n_items_discrepantes": len(panel.get("items_marcados") or []),
            "panel_incompleto": int(bool(panel.get("panel_incompleto"))),
        }
    )
    fila.update(_columnas_coherencia(resultado))
    return fila


def csv_consolidado(resultados: list[dict]) -> str:
    """CSV consolidado: una fila por proyecto (última evaluación completada)."""
    filas = [fila_consolidada(r) for r in resultados]
    columnas: list[str] = []
    for fila in filas:
        for columna in fila:
            if columna not in columnas:
                columnas.append(columna)
    salida = io.StringIO()
    escritor = csv.DictWriter(salida, fieldnames=columnas, lineterminator="\n")
    escritor.writeheader()
    for fila in filas:
        escritor.writerow(fila)
    return salida.getvalue()
