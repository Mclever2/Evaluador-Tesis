"""Configuración del ECM por variables de entorno (.env en la raíz del repo).

Determinismo: la evaluación usa temperature 0, top_p 1 y seed fija. Los tres
jueces usan gpt-4o-mini por defecto. NOTA PARA EL CICLO LONGITUDINAL: se
recomienda diversificar las familias de modelos del panel (p. ej. un juez
OpenAI, uno Anthropic, uno Google) para mitigar el sesgo de auto-preferencia
(Panickssery, Bowman y Feng, 2024); basta con cambiar JUDGE{1,2,3}_MODEL.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""

    judge1_model: str = "gpt-4o-mini"
    judge2_model: str = "gpt-4o-mini"
    judge3_model: str = "gpt-4o-mini"
    eval_temperature: float = 0.0
    eval_seed: int = 42

    embed_model: str = "intfloat/multilingual-e5-small"
    chroma_dir: Path = ROOT / "data" / "chroma"
    results_dir: Path = ROOT / "data" / "results"

    # Trazado opcional con LangSmith (evidencias de pruebas de agentes)
    langsmith_api_key: Optional[str] = None
    langchain_tracing_v2: bool = False

    # Clave simple opcional para proteger el endpoint si se despliega
    app_access_key: Optional[str] = None

    # Supabase opcional (acceso por login y persistencia de historial).
    # Si SUPABASE_URL está configurada, la API exige un token Bearer de un
    # usuario de Supabase (los usuarios se crean desde el panel de Supabase,
    # no hay registro en la app).
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Las rutas relativas del .env (p. ej. RESULTS_DIR=./data/results) se
    # anclan a la raíz del repo: el CWD cambia entre la API (backend/) y los
    # scripts, y sin esto los datos terminan repartidos en dos carpetas.
    if not settings.results_dir.is_absolute():
        settings.results_dir = (ROOT / settings.results_dir).resolve()
    if not settings.chroma_dir.is_absolute():
        settings.chroma_dir = (ROOT / settings.chroma_dir).resolve()
    return settings
