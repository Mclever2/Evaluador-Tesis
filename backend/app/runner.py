"""Ejecución de evaluaciones en segundo plano con progreso consultable.

POST /evaluate devuelve el evaluation_id de inmediato; el grafo corre en un
hilo. El progreso se consume por SSE (GET /evaluations/{id}/events) o por
polling del estado. Registro en memoria por proceso (uvicorn de un worker).
"""

from __future__ import annotations

import json
import queue
import threading
import traceback
from typing import Optional

from anonymizer.anonymizer import ReporteAnonimizacion
from app import storage
from graph.evaluation_graph import ConfigEvaluacion, PanelEvaluador

_SENTINELA_FIN = None


def crear_panel(on_evento) -> PanelEvaluador:
    """Panel real (invocadores OpenAI + RAG opcional). Los tests lo monkeypatchean."""
    from library.store import crear_contexto_rag

    return PanelEvaluador(on_evento=on_evento, contexto_rag=crear_contexto_rag())


class RegistroEvaluaciones:
    def __init__(self) -> None:
        self._colas: dict[str, queue.Queue] = {}
        self._lock = threading.Lock()

    def lanzar(self, evaluation_id: str, project_id: str, config: ConfigEvaluacion) -> None:
        with self._lock:
            self._colas[evaluation_id] = queue.Queue()
        hilo = threading.Thread(
            target=self._ejecutar, args=(evaluation_id, project_id, config), daemon=True
        )
        hilo.start()

    def _emitir(self, evaluation_id: str, evento: Optional[dict]) -> None:
        cola = self._colas.get(evaluation_id)
        if cola is not None:
            cola.put(evento)

    def _ejecutar(self, evaluation_id: str, project_id: str, config: ConfigEvaluacion) -> None:
        try:
            storage.marcar_evaluacion(evaluation_id, "ejecutando")
            self._emitir(evaluation_id, {"tipo": "fase", "detalle": "Preparando la evaluación"})

            doc = storage.cargar_doc_anonimo(project_id)
            reporte = storage.cargar_reporte_indexacion(project_id)
            anonimizacion = (
                ReporteAnonimizacion(**reporte["anonimizacion"])
                if reporte.get("anonimizacion")
                else None
            )

            panel = crear_panel(lambda e: self._emitir(evaluation_id, e))
            resultado = panel.evaluar(doc, anonimizacion, config)

            storage.guardar_resultado(
                evaluation_id, json.loads(resultado.model_dump_json(exclude_none=False))
            )
            self._emitir(
                evaluation_id,
                {"tipo": "completada", "evaluation_id": evaluation_id,
                 "total": resultado.total, "nivel": resultado.nivel},
            )
        except Exception as exc:  # noqa: BLE001 — el error se persiste y reporta
            storage.marcar_evaluacion(evaluation_id, "error", error=f"{exc}")
            self._emitir(evaluation_id, {"tipo": "error", "detalle": str(exc)})
            traceback.print_exc()
        finally:
            self._emitir(evaluation_id, _SENTINELA_FIN)

    def eventos(self, evaluation_id: str):
        """Generador de eventos para SSE; termina con el sentinela."""
        cola = self._colas.get(evaluation_id)
        if cola is None:
            registro = storage.obtener_evaluacion(evaluation_id)
            if registro and registro["estado"] in ("completada", "error"):
                yield {"tipo": registro["estado"], "detalle": registro.get("error") or ""}
            return
        while True:
            try:
                evento = cola.get(timeout=300)
            except queue.Empty:
                return
            if evento is _SENTINELA_FIN:
                with self._lock:
                    self._colas.pop(evaluation_id, None)
                return
            yield evento


registro = RegistroEvaluaciones()
