"""Evaluación por la Batch API de OpenAI (mitad de precio, mismo instrumento). Ver graph/lotes.py.

Pasos (desde backend\\, con EVAL_BATCH_DIR apuntando a una carpeta de trabajo):
  python -m cli.lotes registrar carpeta1 [carpeta2 ...]   arma las solicitudes sin llamar a la API
  python -m cli.lotes resumen                             cuenta solicitudes y estima el costo del lote
  python -m cli.lotes enviar                              sube un lote por modelo
  python -m cli.lotes estado                              estado de los lotes enviados
  python -m cli.lotes descargar                           baja las salidas a respuestas.jsonl
  python -m cli.lotes importar OTRA_CARPETA               reutiliza respuestas de otra carpeta de lotes
Después se evalúa normalmente (cli.batch_eval) con EVAL_BATCH_MODE=usar: el invocador toma cada
respuesta del lote y solo llama en línea a lo que falte (queda anotado en en_linea.jsonl).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from graph import lotes
from graph.llm import PRECIOS_USD_POR_MTOK

DESCUENTO_LOTE = 0.5
# límite de tokens en cola por modelo para esta cuenta, con margen (gpt-4.1: 1,35 M)
MAX_TOKENS_EN_COLA = {"gpt-4.1": 1_100_000, "gpt-4.1-mini": 5_000_000, "gpt-4o-mini": 5_000_000}


def _ascii(t: str) -> str:
    return str(t).encode("ascii", "replace").decode()


def registrar(carpetas: list[str]) -> None:
    os.environ["EVAL_BATCH_MODE"] = "registrar"
    from anonymizer.anonymizer import anonimizar
    from app import runner
    from graph.evaluation_graph import ConfigEvaluacion
    from ingest.extractors import extraer_documento

    archivos = [a for c in carpetas for a in sorted([*Path(c).glob("*.pdf"), *Path(c).glob("*.docx")])]
    for i, archivo in enumerate(archivos, start=1):
        print(f"[{i}/{len(archivos)}] {_ascii(archivo.name)}")
        doc_anonimo, reporte_anon, _ = anonimizar(extraer_documento(archivo))
        panel = runner.crear_panel(lambda e: None)
        config = ConfigEvaluacion(project_id=archivo.stem, rubric_id="dicotomica_v2", mode="completo")
        panel.evaluar(doc_anonimo, reporte_anon, config)  # nada se guarda: solo se registran solicitudes
    resumen()


def _solicitudes() -> dict[str, list[dict]]:
    salida = {}
    for f in sorted(lotes.carpeta().glob("solicitudes_*.jsonl")):
        salida[f.stem.removeprefix("solicitudes_")] = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
    return salida


def resumen() -> None:
    import tiktoken

    total = 0.0
    for modelo, sols in _solicitudes().items():
        enc = tiktoken.encoding_for_model("gpt-4o")
        t_in = sum(len(enc.encode(s["body"]["messages"][0]["content"])) + 200 for s in sols)
        t_out = 900 * len(sols)  # salida típica de las corridas anteriores (estimación conservadora)
        p_in, p_out = PRECIOS_USD_POR_MTOK[modelo]
        usd = (t_in * p_in + t_out * p_out) / 1e6 * DESCUENTO_LOTE
        total += usd
        print(f"{modelo}: {len(sols)} solicitudes, ~{t_in:,} tokens de entrada -> ~US$ {usd:.2f} con el lote")
    print(f"Total estimado con el lote: US$ {total:.2f}")


def _cliente():
    from openai import OpenAI

    from app.config import get_settings

    return OpenAI(api_key=get_settings().openai_api_key)


def _registro() -> Path:
    return lotes.carpeta() / "lotes.json"


def _leer_registro() -> list[dict]:
    if not _registro().exists():
        return []
    reg = json.loads(_registro().read_text(encoding="utf-8"))
    if isinstance(reg, dict):  # formato antiguo: {modelo: {...}}
        reg = [{"modelo": m, **v} for m, v in reg.items()]
    return reg


def _ids_respondidos() -> set[str]:
    destino = lotes.carpeta() / "respuestas.jsonl"
    if not destino.exists():
        return set()
    return {json.loads(x)["custom_id"] for x in destino.read_text(encoding="utf-8").splitlines() if x.strip()}


def enviar() -> None:
    """Envía, por modelo, las solicitudes que aún no tienen respuesta ni están en un lote pendiente."""
    import tiktoken

    enc = tiktoken.encoding_for_model("gpt-4o")
    cliente = _cliente()
    reg = _leer_registro()
    hechos = _ids_respondidos()
    activos: set[str] = set()  # modelos con un lote todavía en curso
    for r in reg:
        b = cliente.batches.retrieve(r["batch_id"])
        if b.status in ("failed", "expired", "cancelled"):
            continue  # sus solicitudes vuelven a quedar pendientes
        if r.get("ids"):
            hechos |= set(r["ids"])
        if b.status in ("validating", "in_progress", "finalizing"):
            activos.add(r["modelo"])
    for modelo, sols in _solicitudes().items():
        pendientes = [s for s in sols if s["custom_id"] not in hechos]
        if not pendientes:
            print(f"{modelo}: nada pendiente")
            continue
        if modelo in activos:
            print(f"{modelo}: {len(pendientes)} pendientes; se envían cuando termine el lote en curso")
            continue
        # el límite de tokens en cola de la cuenta (1,35 M para gpt-4.1) obliga a enviar por partes
        limite = MAX_TOKENS_EN_COLA.get(modelo, 1_000_000)
        parte, acumulado = [], 0
        for s in pendientes:
            t = len(enc.encode(s["body"]["messages"][0]["content"])) + 2_500  # + esquema y salida
            if parte and acumulado + t > limite:
                break
            parte.append(s)
            acumulado += t
        if len(parte) < len(pendientes):
            print(f"{modelo}: se envía una parte ({len(parte)} de {len(pendientes)}, ~{acumulado:,} tokens)")
        pendientes = parte
        archivo_envio = lotes.carpeta() / f"envio_{modelo}_{len(reg) + 1}.jsonl"
        archivo_envio.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in pendientes), encoding="utf-8")
        archivo = cliente.files.create(file=open(archivo_envio, "rb"), purpose="batch")
        lote = cliente.batches.create(input_file_id=archivo.id, endpoint="/v1/chat/completions",
                                      completion_window="24h", metadata={"uso": "tesis-medicion"})
        reg.append({"modelo": modelo, "batch_id": lote.id, "input_file_id": archivo.id,
                    "ids": [x["custom_id"] for x in pendientes]})
        _registro().write_text(json.dumps(reg, indent=1), encoding="utf-8")
        print(f"{modelo}: enviado {lote.id} con {len(pendientes)} solicitudes")


def estado() -> None:
    cliente = _cliente()
    for r in _leer_registro():
        b = cliente.batches.retrieve(r["batch_id"])
        c = b.request_counts
        print(f"{r['modelo']} {r['batch_id'][-8:]}: {b.status} · {c.completed}/{c.total} completadas · {c.failed} fallidas")


def descargar() -> None:
    cliente = _cliente()
    destino = lotes.carpeta() / "respuestas.jsonl"
    ya = _ids_respondidos()
    usd = 0.0
    for r in _leer_registro():
        modelo = r["modelo"]
        b = cliente.batches.retrieve(r["batch_id"])
        if b.status != "completed":
            print(f"{modelo} {r['batch_id'][-8:]}: {b.status}, todavía no se puede descargar")
            continue
        lineas = cliente.files.content(b.output_file_id).text.splitlines() if b.output_file_id else []
        if b.error_file_id:
            (lotes.carpeta() / f"errores_{r['batch_id']}.jsonl").write_text(
                cliente.files.content(b.error_file_id).text, encoding="utf-8")
        nuevas = [x for x in lineas if x.strip() and json.loads(x)["custom_id"] not in ya]
        with open(destino, "a", encoding="utf-8") as fh:
            for x in nuevas:
                fh.write(x + "\n")
        ya |= {json.loads(x)["custom_id"] for x in nuevas}
        p_in, p_out = PRECIOS_USD_POR_MTOK[modelo]
        for x in lineas:
            u = (json.loads(x).get("response") or {}).get("body", {}).get("usage") or {}
            usd += (u.get("prompt_tokens", 0) * p_in + u.get("completion_tokens", 0) * p_out) / 1e6 * DESCUENTO_LOTE
        print(f"{modelo} {r['batch_id'][-8:]}: {len(lineas)} salidas ({len(nuevas)} nuevas)")
    print(f"Costo de los lotes descargados (tokens reales x precio del lote): US$ {usd:.2f}")


def importar(otra: str) -> None:
    """Copia a esta carpeta las respuestas de otra carpeta de lotes (p. ej., un lote de prueba)."""
    origen = Path(otra) / "respuestas.jsonl"
    ya = _ids_respondidos()
    nuevas = [x for x in origen.read_text(encoding="utf-8").splitlines() if x.strip() and json.loads(x)["custom_id"] not in ya]
    with open(lotes.carpeta() / "respuestas.jsonl", "a", encoding="utf-8") as fh:
        for x in nuevas:
            fh.write(x + "\n")
    print(f"{len(nuevas)} respuestas importadas de {origen}")


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    accion, resto = argv[0], argv[1:]
    {"registrar": lambda: registrar(resto), "resumen": resumen, "enviar": enviar, "estado": estado,
     "descargar": descargar, "importar": lambda: importar(resto[0])}[accion]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
