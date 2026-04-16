"""
S1: API authentication middleware.
Protects /api/* endpoints with a simple API key from .env.
Dashboard pages are public (or can be gated with session auth later).
"""
from __future__ import annotations

import os
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key() -> str:
    return os.environ.get("WEB_API_KEY", "")


async def verify_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    expected = get_api_key()
    if not expected:
        # No key configured = API is open (dev mode)
        return "dev"
    if not api_key or api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return api_key
