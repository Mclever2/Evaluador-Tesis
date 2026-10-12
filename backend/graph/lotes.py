"""Modo por lotes del invocador (Batch API de OpenAI, a la mitad del precio).

No cambia el instrumento: cada solicitud es la misma que el invocador enviaría en línea (mismo modelo,
prompt, esquema de salida, temperature 0, top_p 1 y semilla), porque el cuerpo se arma con el propio
`ChatOpenAI` y la respuesta se interpreta con el mismo parser del SDK de OpenAI que usa langchain.

Se controla con variables de entorno:
  EVAL_BATCH_MODE  ""          modo normal (llamadas en línea)
                   "registrar" no llama a la API: guarda cada solicitud en EVAL_BATCH_DIR y responde
                               como si la llamada fallara (el grafo degrada; nada se guarda como resultado)
                   "usar"      responde con las salidas descargadas del lote; si una solicitud no está en
                               el lote, o su salida no es válida, la hace en línea (y lo anota)
  EVAL_BATCH_DIR   carpeta con solicitudes_<modelo>.jsonl, respuestas.jsonl y en_linea.jsonl

El envío, la consulta y la descarga de los lotes están en cli/lotes.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Type

from pydantic import BaseModel

_LOCK = threading.Lock()
_VISTOS: dict[Path, set[str]] = {}
_RESPUESTAS: dict[str, dict] | None = None


class PendienteBatch(RuntimeError):
    """En modo registrar: la solicitud quedó guardada para el lote; no hay respuesta todavía."""


def modo() -> str:
    return os.environ.get("EVAL_BATCH_MODE", "").strip().lower()


def carpeta() -> Path:
    ruta = os.environ.get("EVAL_BATCH_DIR", "").strip()
    if not ruta:
        raise RuntimeError("EVAL_BATCH_DIR no está definido")
    p = Path(ruta)
    p.mkdir(parents=True, exist_ok=True)
    return p


def cuerpo(llm: Any, prompt: str, schema: Type[BaseModel]) -> dict:
    """Cuerpo exacto de /v1/chat/completions que langchain enviaría con with_structured_output."""
    from langchain_core.messages import HumanMessage
    from openai.lib._parsing._completions import type_to_response_format_param

    payload = llm._get_request_payload([HumanMessage(content=prompt)], response_format=schema)
    payload.pop("stream", None)
    payload["response_format"] = type_to_response_format_param(schema)
    return json.loads(json.dumps(payload, ensure_ascii=False))


def clave(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def registrar(body: dict) -> str:
    k = clave(body)
    archivo = carpeta() / f"solicitudes_{body['model']}.jsonl"
    with _LOCK:
        if archivo not in _VISTOS:
            _VISTOS[archivo] = set()
            if archivo.exists():
                for linea in archivo.read_text(encoding="utf-8").splitlines():
                    if linea.strip():
                        _VISTOS[archivo].add(json.loads(linea)["custom_id"])
        if k not in _VISTOS[archivo]:
            with open(archivo, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"custom_id": k, "method": "POST", "url": "/v1/chat/completions",
                                     "body": body}, ensure_ascii=False) + "\n")
            _VISTOS[archivo].add(k)
    return k


def respuesta(body: dict) -> dict | None:
    """Cuerpo de la respuesta del lote para esta solicitud, o None si no está o falló."""
    global _RESPUESTAS
    with _LOCK:
        if _RESPUESTAS is None:
            _RESPUESTAS = {}
            archivo = carpeta() / "respuestas.jsonl"
            if archivo.exists():
                for linea in archivo.read_text(encoding="utf-8").splitlines():
                    if not linea.strip():
                        continue
                    r = json.loads(linea)
                    resp = r.get("response") or {}
                    if resp.get("status_code") == 200 and not r.get("error"):
                        _RESPUESTAS[r["custom_id"]] = resp["body"]
    return _RESPUESTAS.get(clave(body))


def interpretar(body_respuesta: dict, schema: Type[BaseModel]) -> tuple[BaseModel, int, int]:
    """Misma interpretación que el SDK aplica en chat.completions.parse (la que usa langchain)."""
    from openai._types import omit
    from openai.lib._parsing._completions import parse_chat_completion
    from openai.types.chat import ChatCompletion

    cc = ChatCompletion.model_validate(body_respuesta)
    parsed = parse_chat_completion(response_format=schema, input_tools=omit, chat_completion=cc)
    objeto = parsed.choices[0].message.parsed
    if objeto is None:
        raise ValueError("la salida del lote no contiene el JSON esperado")
    uso = body_respuesta.get("usage") or {}
    return objeto, int(uso.get("prompt_tokens", 0)), int(uso.get("completion_tokens", 0))


def anotar_en_linea(body: dict, motivo: str) -> None:
    with _LOCK:
        with open(carpeta() / "en_linea.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"custom_id": clave(body), "modelo": body.get("model"), "motivo": motivo},
                                ensure_ascii=False) + "\n")


def vacio(schema: Type[BaseModel]) -> BaseModel | None:
    """Respuesta neutra para los análisis de coherencia en modo registrar: permite que el análisis siga y
    registre todas sus solicitudes (p. ej., la justificación después de la descripción del problema)."""
    try:
        return schema.model_validate({"etiquetas": [], "contradicciones": []})
    except Exception:  # noqa: BLE001
        return None
