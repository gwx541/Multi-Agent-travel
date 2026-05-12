"""鉴权依赖：解析 JWT 与开发模式下的匿名 user_id。"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.memory.memory_store import memory_store
from backend.schemas import ChatRequest

from backend.auth.tokens import decode_access_token

security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    factory = memory_store.get_session_factory()
    async with factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]


def _sub_from_bearer(credentials: HTTPAuthorizationCredentials | None) -> str | None:
    if not credentials or credentials.scheme.lower() != "bearer":
        return None
    try:
        payload = decode_access_token(credentials.credentials)
    except PyJWTError:
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None


async def chat_effective_user_id(
    req: ChatRequest,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(security)
    ],
) -> str:
    uid = _sub_from_bearer(credentials)
    if uid:
        return uid
    if settings.auth_required:
        raise HTTPException(
            status_code=401,
            detail="需要登录：请在 Authorization 头携带 Bearer JWT",
        )
    # 单用户模式：请求带了 user_id 就用它（向后兼容旧前端），否则回退默认。
    legacy = (req.user_id or "").strip()
    return legacy or settings.default_user_id


async def memory_effective_user_id(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(security)
    ],
    legacy_user_id: str | None = Query(
        None,
        alias="user_id",
        description="仅 AUTH_REQUIRED=false 时可用；不传则用 DEFAULT_USER_ID",
    ),
) -> str:
    uid = _sub_from_bearer(credentials)
    if uid:
        return uid
    if settings.auth_required:
        raise HTTPException(status_code=401, detail="需要登录")
    legacy = (legacy_user_id or "").strip()
    return legacy or settings.default_user_id
