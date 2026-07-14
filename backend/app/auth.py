"""Verificación de acceso a la API.

Modos, en orden de precedencia:
1. Supabase configurado (SUPABASE_URL + SUPABASE_ANON_KEY): se exige un token
   Bearer de un usuario de Supabase Auth. La app NO registra usuarios: se
   crean desde el panel de Supabase (Authentication → Users).
2. Solo APP_ACCESS_KEY: clave simple por encabezado X-Access-Key.
3. Nada configurado: API abierta (uso local).

La validación del token se hace contra {SUPABASE_URL}/auth/v1/user (funciona
con cualquier esquema de firma del proyecto) y se cachea unos minutos para no
añadir una llamada de red por request.
"""

from __future__ import annotations

import time
from typing import Optional

from app.config import get_settings

_TTL_CACHE_SEG = 300
_cache_tokens: dict[str, float] = {}  # token → expira_en (epoch)


def _validar_contra_supabase(token: str) -> bool:
    import httpx

    settings = get_settings()
    try:
        respuesta = httpx.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": settings.supabase_anon_key or "",
            },
            timeout=10,
        )
        return respuesta.status_code == 200
    except Exception:
        return False


def token_valido(token: Optional[str]) -> bool:
    """True si el token Bearer corresponde a un usuario vigente de Supabase."""
    if not token:
        return False
    ahora = time.time()
    expira = _cache_tokens.get(token)
    if expira and expira > ahora:
        return True
    if _validar_contra_supabase(token):
        if len(_cache_tokens) > 256:  # el panel de un solo equipo no pasa de aquí
            _cache_tokens.clear()
        _cache_tokens[token] = ahora + _TTL_CACHE_SEG
        return True
    return False


def modo_acceso() -> str:
    settings = get_settings()
    if settings.supabase_url and settings.supabase_anon_key:
        return "supabase"
    if settings.app_access_key:
        return "clave"
    return "abierto"
