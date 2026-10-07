"""Completa evaluaciones ya guardadas con los análisis de coherencia, sin repetir la rúbrica.

Agrega a cada resultado JSON el índice argumentativo (Toulmin) y la coherencia global. Usa el MISMO
documento anonimizado que vieron los jueces (data/projects) y la misma segmentación por reglas. Los
puntajes de la rúbrica no se tocan. Antes de escribir, copia el JSON original en
data/results/_respaldo_coherencia/.

Uso (desde backend/):
  python -m cli.coherencia ..\\data\\results\\eval_xxx.json [más JSON...] [--forzar]

--forzar vuelve a calcular aunque el resultado ya tenga ambos análisis.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from app import storage
from app.config import get_settings
from graph.evaluation_graph import aplicar_analisis_coherencia
from graph.llm import crear_invocador
from graph.schemas import EvaluacionResultado
from graph.segmenter import segmentar
from graph.segmenter_llm import crear_fallback_llm
from rubrics import load_rubric


def completar(ruta: Path, invocador, modelo: str, forzar: bool = False) -> str:
    resultado = EvaluacionResultado.model_validate_json(ruta.read_text(encoding="utf-8"))
    if resultado.argumentacion and resultado.coherencia_global and not forzar:
        return "ya tenía ambos análisis (use --forzar para recalcular)"
    registro = storage.obtener_evaluacion(ruta.stem)
    if not registro:
        raise ValueError(f"la evaluación {ruta.stem} no está en el índice del evaluador")
    doc = storage.cargar_doc_anonimo(registro["project_id"])
    rubrica = load_rubric(resultado.rubric_id)
    fallback = None
    if resultado.reporte_indexacion.get("metodo") != "heuristica":  # reproducir el respaldo LLM del grafo
        fallback = crear_fallback_llm(crear_invocador(get_settings().judge1_model))
    segmentacion = segmentar(doc, rubrica, fallback_llm=fallback)
    respaldo = ruta.parent / "_respaldo_coherencia" / ruta.name
    if not respaldo.exists():
        respaldo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ruta, respaldo)
    aplicar_analisis_coherencia(resultado, segmentacion, invocador, modelo)
    ruta.write_text(json.dumps(json.loads(resultado.model_dump_json(exclude_none=False)), ensure_ascii=False,
                               indent=2), encoding="utf-8")
    arg, coh = resultado.argumentacion, resultado.coherencia_global
    return (f"índice argumentativo {arg.indice_proyecto if arg else '-'} · "
            f"coherencia global {coh.nota if coh else '-'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Completa evaluaciones con los análisis de coherencia")
    parser.add_argument("resultados", nargs="+", help="Rutas de los JSON de resultado (eval_*.json)")
    parser.add_argument("--forzar", action="store_true")
    args = parser.parse_args(argv)
    settings = get_settings()
    invocador = crear_invocador(settings.analysis_model, settings)
    errores = 0
    for texto in args.resultados:
        ruta = Path(texto)
        try:
            print(f"{ruta.name}: {completar(ruta, invocador, settings.analysis_model, args.forzar)}")
        except Exception as exc:  # noqa: BLE001 — un resultado no detiene el lote
            errores += 1
            print(f"{ruta.name}: ERROR {exc}")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
