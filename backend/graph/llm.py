"""Invocador LLM del panel: salida estructurada, determinismo y reintentos.

Determinismo del instrumento: temperature 0, top_p 1 y seed fija (si el
proveedor la soporta). Los jueces usan gpt-4o-mini por defecto; para el ciclo
longitudinal se recomienda diversificar familias de modelos en el panel para
mitigar el sesgo de auto-preferencia (ver README y app/config.py).

El `Invocador` es una función (prompt, schema) → (parsed, UsoLLM). Los tests
inyectan dobles con la misma firma: nada en graph/ llama a OpenAI directamente.
"""

from __future__ import annotations

from typing import Callable, Type

from pydantic import BaseModel

from app.config import Settings, get_settings

# Precios referenciales USD por millón de tokens (entrada, salida) para estimar
# el costo registrado en cada resultado. Modelos fuera de la tabla → None.
PRECIOS_USD_POR_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
}


class UsoLLM(BaseModel):
    tokens_entrada: int = 0
    tokens_salida: int = 0
    lote: bool = False  # respuesta obtenida por la Batch API (se cobra a la mitad del precio)


Invocador = Callable[[str, Type[BaseModel]], tuple[BaseModel, UsoLLM]]


def costo_usd(modelo: str, tokens_entrada: int, tokens_salida: int) -> float | None:
    precios = PRECIOS_USD_POR_MTOK.get(modelo)
    if precios is None:
        return None
    entrada, salida = precios
    return round((tokens_entrada * entrada + tokens_salida * salida) / 1_000_000, 6)


def crear_invocador(modelo: str, settings: Settings | None = None) -> Invocador:
    """Invocador real sobre langchain-openai, con backoff exponencial."""
    from langchain_openai import ChatOpenAI
    from tenacity import retry, stop_after_attempt, wait_exponential

    settings = settings or get_settings()
    llm = ChatOpenAI(
        model=modelo,
        temperature=settings.eval_temperature,
        top_p=1.0,
        seed=settings.eval_seed,
        api_key=settings.openai_api_key,
        max_retries=0,  # los reintentos los maneja tenacity (backoff exponencial)
        timeout=120,
    )

    from graph import lotes
    from tenacity import retry_if_not_exception_type

    @retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(4), reraise=True,
           retry=retry_if_not_exception_type(lotes.PendienteBatch))
    def _invocar(prompt: str, schema: Type[BaseModel]) -> tuple[BaseModel, UsoLLM]:
        modo_lote = lotes.modo()
        if modo_lote == "registrar":
            lotes.registrar(lotes.cuerpo(llm, prompt, schema))
            neutra = lotes.vacio(schema)
            if neutra is not None and schema.__name__ in ("RespuestaArgumentacion", "RespuestaCoherencia"):
                return neutra, UsoLLM()
            raise lotes.PendienteBatch("solicitud registrada para el lote")
        if modo_lote == "usar":
            body = lotes.cuerpo(llm, prompt, schema)
            resp = lotes.respuesta(body)
            if resp is not None:
                try:
                    parsed, t_in, t_out = lotes.interpretar(resp, schema)
                    return parsed, UsoLLM(tokens_entrada=t_in, tokens_salida=t_out, lote=True)
                except Exception as exc:  # noqa: BLE001 — salida inválida: se repite en línea
                    lotes.anotar_en_linea(body, f"salida del lote no válida: {exc}")
            else:
                lotes.anotar_en_linea(body, "no está en el lote")
        estructurado = llm.with_structured_output(schema, include_raw=True)
        salida = estructurado.invoke(prompt)
        parsed = salida.get("parsed")
        if parsed is None:
            error = salida.get("parsing_error")
            raise ValueError(f"El modelo {modelo} no devolvió el JSON esperado: {error}")
        raw = salida.get("raw")
        uso = getattr(raw, "usage_metadata", None) or {}
        return parsed, UsoLLM(
            tokens_entrada=int(uso.get("input_tokens", 0)),
            tokens_salida=int(uso.get("output_tokens", 0)),
        )

    return _invocar


def crear_invocadores_panel(settings: Settings | None = None) -> dict[int, Invocador]:
    settings = settings or get_settings()
    modelos = {1: settings.judge1_model, 2: settings.judge2_model, 3: settings.judge3_model}
    return {n: crear_invocador(m, settings) for n, m in modelos.items()}
