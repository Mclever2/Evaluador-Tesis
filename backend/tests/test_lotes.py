"""Modo por lotes: el cuerpo registrado es el que langchain envía en línea y la respuesta se interpreta igual."""

import json

import httpx
import pytest

from graph import lotes
from graph.schemas import RespuestaArgumentacion

RESPUESTA = {
    "id": "x", "object": "chat.completion", "created": 0, "model": "gpt-4.1",
    "choices": [{"index": 0, "finish_reason": "stop", "message": {
        "role": "assistant",
        "content": json.dumps({"etiquetas": [{"id": 1, "funcion": "afirmacion", "responde_en": None}]})}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


def _llm(capturado: dict):
    from langchain_openai import ChatOpenAI

    def handler(req):
        capturado["body"] = json.loads(req.content)
        return httpx.Response(200, json=RESPUESTA)

    return ChatOpenAI(model="gpt-4.1", temperature=0, top_p=1.0, seed=42, api_key="sk-test", max_retries=0,
                      http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_cuerpo_igual_al_de_la_llamada_en_linea():
    capturado: dict = {}
    llm = _llm(capturado)
    salida = llm.with_structured_output(RespuestaArgumentacion, include_raw=True).invoke("Clasifica: [1] Algo.")
    cuerpo = lotes.cuerpo(llm, "Clasifica: [1] Algo.", RespuestaArgumentacion)
    en_linea = {k: v for k, v in capturado["body"].items() if k != "stream"}
    assert cuerpo == en_linea
    objeto, t_in, t_out = lotes.interpretar(RESPUESTA, RespuestaArgumentacion)
    assert objeto == salida["parsed"] and (t_in, t_out) == (10, 5)


def test_registrar_y_usar(tmp_path, monkeypatch):
    from graph.llm import crear_invocador

    monkeypatch.setenv("EVAL_BATCH_DIR", str(tmp_path))
    monkeypatch.setenv("EVAL_BATCH_MODE", "registrar")
    monkeypatch.setattr(lotes, "_RESPUESTAS", None)
    monkeypatch.setattr(lotes, "_VISTOS", {})
    invocar = crear_invocador("gpt-4.1")
    neutra, _ = invocar("Clasifica: [1] Algo.", RespuestaArgumentacion)
    assert neutra.etiquetas == []
    linea = json.loads((tmp_path / "solicitudes_gpt-4.1.jsonl").read_text(encoding="utf-8"))
    (tmp_path / "respuestas.jsonl").write_text(json.dumps(
        {"custom_id": linea["custom_id"], "response": {"status_code": 200, "body": RESPUESTA}, "error": None}) + "\n",
        encoding="utf-8")
    monkeypatch.setenv("EVAL_BATCH_MODE", "usar")
    parsed, uso = invocar("Clasifica: [1] Algo.", RespuestaArgumentacion)
    assert parsed.etiquetas[0].funcion == "afirmacion" and uso.lote and uso.tokens_entrada == 10
    assert not (tmp_path / "en_linea.jsonl").exists()


def test_registrar_panel_lanza_pendiente(tmp_path, monkeypatch):
    from graph.llm import crear_invocador
    from graph.schemas import RespuestaTransversales

    monkeypatch.setenv("EVAL_BATCH_DIR", str(tmp_path))
    monkeypatch.setenv("EVAL_BATCH_MODE", "registrar")
    monkeypatch.setattr(lotes, "_VISTOS", {})
    with pytest.raises(lotes.PendienteBatch):
        crear_invocador("gpt-4o-mini")("Evalúa el texto.", RespuestaTransversales)
