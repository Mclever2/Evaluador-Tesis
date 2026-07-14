"""Persistencia mínima del ECM.

- Cada evaluación se guarda como JSON en data/results/ y se registra en un
  índice SQLite simple (data/ecm.sqlite3).
- Cada proyecto subido guarda en data/projects/{id}/ el documento ya
  anonimizado, el reporte de indexación y el mapeo de anonimización
  (trazabilidad LOCAL: el mapeo jamás se envía al LLM).
- Sin cuentas de usuario, sin historial de uso por estudiante, sin analítica.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import ROOT, get_settings
from ingest.extractors import DocumentoExtraido

DATA_DIR = ROOT / "data"
PROJECTS_DIR = DATA_DIR / "projects"
DB_PATH = DATA_DIR / "ecm.sqlite3"


def results_dir() -> Path:
    return Path(get_settings().results_dir)


def _conn() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(DB_PATH, check_same_thread=False)
    conexion.row_factory = sqlite3.Row
    return conexion


def init_db() -> None:
    with _conn() as conexion:
        conexion.executescript(
            """
            CREATE TABLE IF NOT EXISTS proyectos (
                id TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                tipo TEXT NOT NULL,
                paginas INTEGER,
                palabras INTEGER,
                subido_en TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evaluaciones (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES proyectos(id),
                rubric_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                estado TEXT NOT NULL,           -- pendiente | ejecutando | completada | error
                creado_en TEXT NOT NULL,
                total REAL,
                nivel TEXT,
                error TEXT,
                ruta_json TEXT
            );
            """
        )


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nuevo_id(prefijo: str) -> str:
    return f"{prefijo}_{uuid.uuid4().hex[:12]}"


# ── Proyectos ────────────────────────────────────────────────────────────────


def guardar_proyecto(
    doc_anonimo: DocumentoExtraido, reporte_indexacion: dict, mapeo: dict[str, str]
) -> str:
    init_db()
    project_id = _nuevo_id("proj")
    carpeta = PROJECTS_DIR / project_id
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "doc_anonimo.json").write_text(doc_anonimo.model_dump_json(), encoding="utf-8")
    (carpeta / "index_report.json").write_text(
        json.dumps(reporte_indexacion, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Mapeo de anonimización: SOLO trazabilidad local. No se expone por API.
    (carpeta / "mapeo_anonimizacion.json").write_text(
        json.dumps(mapeo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with _conn() as conexion:
        conexion.execute(
            "INSERT INTO proyectos (id, nombre, tipo, paginas, palabras, subido_en) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                project_id,
                doc_anonimo.nombre,
                doc_anonimo.tipo,
                len(doc_anonimo.paginas),
                doc_anonimo.total_palabras,
                _ahora(),
            ),
        )
    return project_id


def obtener_proyecto(project_id: str) -> Optional[dict]:
    init_db()
    with _conn() as conexion:
        fila = conexion.execute("SELECT * FROM proyectos WHERE id = ?", (project_id,)).fetchone()
    return dict(fila) if fila else None


def cargar_doc_anonimo(project_id: str) -> DocumentoExtraido:
    ruta = PROJECTS_DIR / project_id / "doc_anonimo.json"
    return DocumentoExtraido.model_validate_json(ruta.read_text(encoding="utf-8"))


def cargar_reporte_indexacion(project_id: str) -> dict:
    ruta = PROJECTS_DIR / project_id / "index_report.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


# ── Evaluaciones ─────────────────────────────────────────────────────────────


def crear_evaluacion(project_id: str, rubric_id: str, mode: str) -> str:
    init_db()
    evaluation_id = _nuevo_id("eval")
    with _conn() as conexion:
        conexion.execute(
            "INSERT INTO evaluaciones (id, project_id, rubric_id, mode, estado, creado_en) "
            "VALUES (?, ?, ?, ?, 'pendiente', ?)",
            (evaluation_id, project_id, rubric_id, mode, _ahora()),
        )
    return evaluation_id


def marcar_evaluacion(
    evaluation_id: str,
    estado: str,
    total: Optional[float] = None,
    nivel: Optional[str] = None,
    error: Optional[str] = None,
    ruta_json: Optional[str] = None,
) -> None:
    with _conn() as conexion:
        conexion.execute(
            "UPDATE evaluaciones SET estado = ?, total = COALESCE(?, total), "
            "nivel = COALESCE(?, nivel), error = COALESCE(?, error), "
            "ruta_json = COALESCE(?, ruta_json) WHERE id = ?",
            (estado, total, nivel, error, ruta_json, evaluation_id),
        )


def guardar_resultado(evaluation_id: str, resultado: dict) -> Path:
    destino = results_dir()
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"{evaluation_id}.json"
    ruta.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    marcar_evaluacion(
        evaluation_id,
        "completada",
        total=resultado.get("total"),
        nivel=resultado.get("nivel"),
        ruta_json=str(ruta),
    )
    return ruta


def obtener_evaluacion(evaluation_id: str) -> Optional[dict]:
    init_db()
    with _conn() as conexion:
        fila = conexion.execute(
            "SELECT * FROM evaluaciones WHERE id = ?", (evaluation_id,)
        ).fetchone()
    if fila is None:
        return None
    registro = dict(fila)
    if registro.get("ruta_json") and Path(registro["ruta_json"]).exists():
        registro["resultado"] = json.loads(
            Path(registro["ruta_json"]).read_text(encoding="utf-8")
        )
    return registro


def evaluaciones_completadas(rubric_id: Optional[str] = None) -> list[dict]:
    """Última evaluación completada por proyecto (para el CSV consolidado)."""
    init_db()
    consulta = (
        "SELECT e.* FROM evaluaciones e "
        "JOIN (SELECT project_id, MAX(creado_en) AS m FROM evaluaciones "
        "      WHERE estado = 'completada' {filtro} GROUP BY project_id) ult "
        "ON e.project_id = ult.project_id AND e.creado_en = ult.m "
        "WHERE e.estado = 'completada' {filtro_e} ORDER BY e.creado_en"
    )
    filtro = "AND rubric_id = ?" if rubric_id else ""
    consulta = consulta.format(filtro=filtro, filtro_e=filtro.replace("rubric_id", "e.rubric_id"))
    parametros = (rubric_id, rubric_id) if rubric_id else ()
    with _conn() as conexion:
        filas = conexion.execute(consulta, parametros).fetchall()
    registros = []
    for fila in filas:
        registro = dict(fila)
        if registro.get("ruta_json") and Path(registro["ruta_json"]).exists():
            registro["resultado"] = json.loads(
                Path(registro["ruta_json"]).read_text(encoding="utf-8")
            )
            registros.append(registro)
    return registros
