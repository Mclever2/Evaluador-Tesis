"""API del ECM (FastAPI).

Endpoints del plan:
- POST /projects/upload                    → project_id + reporte de indexación
- GET  /projects/{id}/index-report         → segmentación y anonimización
- POST /projects/{id}/evaluate             → evaluation_id (grafo en segundo plano)
- GET  /evaluations/{id}                   → estado + JSON completo
- GET  /evaluations/{id}/events            → progreso por SSE
- GET  /evaluations/{id}/export?format=    → JSON o CSV plano
- GET  /evaluations/export/consolidated.csv→ una fila por proyecto
- POST /evaluations/{id}/chat              → preguntas sobre el informe
- GET  /rubrics, /library, /health

Protección opcional: si APP_ACCESS_KEY está configurada, toda la API exige el
encabezado X-Access-Key (clave simple; sin cuentas de usuario).
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from anonymizer.anonymizer import anonimizar
from app import chat as chat_mod
from app import exporters, storage
from app.config import get_settings
from app.runner import registro
from graph.evaluation_graph import ConfigEvaluacion
from graph.segmenter import segmentar
from ingest.extractors import extraer_documento
from rubrics import load_rubric, rubricas_disponibles


def verificar_acceso(
    x_access_key: Optional[str] = Header(default=None),
    authorization: Optional[str] = Header(default=None),
) -> None:
    from app import auth

    modo = auth.modo_acceso()
    if modo == "supabase":
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if not auth.token_valido(token):
            raise HTTPException(
                status_code=401,
                detail="Sesión de Supabase inválida o expirada: inicia sesión de nuevo",
            )
        return
    if modo == "clave" and x_access_key != get_settings().app_access_key:
        raise HTTPException(status_code=401, detail="Clave de acceso inválida")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    storage.init_db()
    yield


app = FastAPI(
    title="ECM — Evaluador de Calidad Metodológica",
    description="Instrumento de medición: evalúa proyectos de tesis con un panel de jueces LLM.",
    version="1.0.0",
    lifespan=lifespan,
    dependencies=[Depends(verificar_acceso)],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Proyectos ────────────────────────────────────────────────────────────────


@app.post("/projects/upload")
async def subir_proyecto(archivo: UploadFile = File(...)) -> dict:
    sufijo = Path(archivo.filename or "").suffix.lower()
    if sufijo not in (".pdf", ".docx"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .pdf o .docx")

    temporal = storage.DATA_DIR / "tmp"
    temporal.mkdir(parents=True, exist_ok=True)
    ruta_tmp = temporal / f"subida{sufijo}"
    ruta_tmp.write_bytes(await archivo.read())
    try:
        doc = extraer_documento(ruta_tmp)
        doc.nombre = archivo.filename or doc.nombre
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        ruta_tmp.unlink(missing_ok=True)

    # Anonimización ANTES de cualquier LLM; segmentación heurística para el
    # reporte inmediato (el respaldo LLM corre recién al evaluar).
    doc_anonimo, reporte_anon, mapeo = anonimizar(doc)
    rubrica = load_rubric("especifica_v1")
    segmentacion = segmentar(doc_anonimo, rubrica)
    segmentacion.anonimizacion = reporte_anon

    project_id = storage.guardar_proyecto(doc_anonimo, segmentacion.reporte(), mapeo)
    return {
        "project_id": project_id,
        "nombre": doc.nombre,
        "tipo": doc.tipo,
        "paginas": len(doc.paginas),
        "palabras": doc.total_palabras,
        "estado": "indexado",
        "reporte_indexacion": segmentacion.reporte(),
    }


@app.get("/projects/{project_id}/index-report")
def reporte_indexacion(project_id: str) -> dict:
    if storage.obtener_proyecto(project_id) is None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    return storage.cargar_reporte_indexacion(project_id)


# ── Evaluaciones ─────────────────────────────────────────────────────────────


class EvaluarRequest(BaseModel):
    rubric: str = "especifica_v1"
    mode: Literal["completo", "progresivo"] = "completo"
    semanas_activas: Optional[list[int]] = None
    incluir_administrativos: bool = True


@app.post("/projects/{project_id}/evaluate")
def evaluar(project_id: str, cuerpo: EvaluarRequest) -> dict:
    if storage.obtener_proyecto(project_id) is None:
        raise HTTPException(status_code=404, detail="Proyecto no encontrado")
    try:
        load_rubric(cuerpo.rubric)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    evaluation_id = storage.crear_evaluacion(project_id, cuerpo.rubric, cuerpo.mode)
    config = ConfigEvaluacion(
        project_id=project_id,
        rubric_id=cuerpo.rubric,
        mode=cuerpo.mode,
        semanas_activas=cuerpo.semanas_activas,
        incluir_administrativos=cuerpo.incluir_administrativos,
    )
    registro.lanzar(evaluation_id, project_id, config)
    return {"evaluation_id": evaluation_id, "estado": "pendiente"}


@app.get("/evaluations/export/consolidated.csv")
def exportar_consolidado(rubric: Optional[str] = None) -> Response:
    registros = storage.evaluaciones_completadas(rubric)
    csv_texto = exporters.csv_consolidado([r["resultado"] for r in registros])
    return Response(
        content=csv_texto,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=consolidado_ecm.csv"},
    )


@app.get("/evaluations/{evaluation_id}")
def obtener_evaluacion(evaluation_id: str) -> dict:
    registro_eval = storage.obtener_evaluacion(evaluation_id)
    if registro_eval is None:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada")
    return registro_eval


@app.get("/evaluations/{evaluation_id}/events")
async def eventos_evaluacion(evaluation_id: str) -> EventSourceResponse:
    if storage.obtener_evaluacion(evaluation_id) is None:
        raise HTTPException(status_code=404, detail="Evaluación no encontrada")

    def generador():
        for evento in registro.eventos(evaluation_id):
            yield {"data": json.dumps(evento, ensure_ascii=False)}

    return EventSourceResponse(generador())


@app.get("/evaluations/{evaluation_id}/export")
def exportar_evaluacion(evaluation_id: str, format: Literal["json", "csv"] = "json") -> Response:
    registro_eval = storage.obtener_evaluacion(evaluation_id)
    if registro_eval is None or "resultado" not in registro_eval:
        raise HTTPException(status_code=404, detail="Evaluación no disponible")
    resultado = registro_eval["resultado"]
    if format == "json":
        return Response(
            content=json.dumps(resultado, ensure_ascii=False, indent=2),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={evaluation_id}.json"},
        )
    return Response(
        content=exporters.csv_items(resultado),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={evaluation_id}.csv"},
    )


class ChatRequest(BaseModel):
    pregunta: str


@app.post("/evaluations/{evaluation_id}/chat")
def chat_informe(evaluation_id: str, cuerpo: ChatRequest) -> dict:
    registro_eval = storage.obtener_evaluacion(evaluation_id)
    if registro_eval is None or "resultado" not in registro_eval:
        raise HTTPException(status_code=404, detail="Evaluación no disponible")
    resultado = registro_eval["resultado"]
    rubrica = load_rubric(resultado["rubric_id"])
    respuesta, uso = chat_mod.responder_pregunta(
        resultado, rubrica, cuerpo.pregunta, chat_mod.invocador_por_defecto()
    )
    return {"respuesta": respuesta, "tokens": uso.tokens_entrada + uso.tokens_salida}


# ── Catálogos y estado ───────────────────────────────────────────────────────


@app.get("/rubrics")
def listar_rubricas() -> list[dict]:
    catalogo = []
    for rubric_id in rubricas_disponibles():
        rubrica = load_rubric(rubric_id)
        catalogo.append(
            {
                "id": rubrica.id,
                "nombre": rubrica.nombre,
                "tipo": rubrica.tipo,
                "puntaje_maximo": rubrica.puntaje_maximo,
                "secciones": len(rubrica.secciones),
                "items": rubrica.total_items,
            }
        )
    return catalogo


@app.get("/library")
def biblioteca() -> dict:
    from library.store import libros_ingresados

    return {"libros": libros_ingresados()}


@app.get("/health")
def salud() -> dict:
    return {"estado": "ok", "servicio": "ecm-backend"}
