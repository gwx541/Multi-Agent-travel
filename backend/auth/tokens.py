"""JWT 访问令牌。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from backend.config import settings


def create_access_token(sub: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=max(1, settings.jwt_expire_minutes))
    return jwt.encode(
        {"sub": sub, "iat": now, "exp": exp},
        settings.jwt_secret,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> dict:
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=["HS256"],
    )
