"""注册 / 登录 / 当前用户。"""
from __future__ import annotations

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from jwt.exceptions import PyJWTError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.auth.deps import DbSession
from backend.auth.passwords import hash_password, verify_password
from backend.auth.tokens import create_access_token, decode_access_token
from backend.config import settings
from backend.db.models import Account, User
from backend.memory.memory_store import memory_store

router = APIRouter(prefix="/api/auth", tags=["auth"])
_bearer_required = HTTPBearer()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterBody(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        s = v.strip().lower()
        if not _EMAIL_RE.match(s):
            raise ValueError("邮箱格式不正确")
        return s


class LoginBody(RegisterBody):
    pass


class UserPublic(BaseModel):
    id: str
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterBody, db: DbSession) -> TokenResponse:
    if not settings.auth_required:
        raise HTTPException(
            status_code=400,
            detail="当前 AUTH_REQUIRED=false，无需注册；开发模式请直接用 user_id 调接口",
        )
    uid = str(uuid.uuid4())
    acc = Account(id=uid, email=body.email, password_hash=hash_password(body.password))
    mem_user = User(user_id=uid)
    db.add(acc)
    db.add(mem_user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="该邮箱已注册") from None
    token = create_access_token(uid)
    return TokenResponse(access_token=token, user=UserPublic(id=uid, email=body.email))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginBody, db: DbSession) -> TokenResponse:
    if not settings.auth_required:
        raise HTTPException(
            status_code=400,
            detail="当前 AUTH_REQUIRED=false，无需登录",
        )
    row = await db.scalar(select(Account).where(Account.email == body.email))
    if row is None or not verify_password(body.password, row.password_hash):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    token = create_access_token(row.id)
    return TokenResponse(access_token=token, user=UserPublic(id=row.id, email=row.email))


class MeResponse(BaseModel):
    user: UserPublic


@router.get("/me", response_model=MeResponse)
async def me(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_required)],
) -> MeResponse:
    try:
        payload = decode_access_token(credentials.credentials)
    except PyJWTError:
        raise HTTPException(status_code=401, detail="令牌无效或已过期") from None
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="无效令牌")

    factory = memory_store.get_session_factory()
    async with factory() as session:
        acc = await session.get(Account, str(sub))
        if acc is None:
            raise HTTPException(status_code=401, detail="账户不存在")
        return MeResponse(user=UserPublic(id=acc.id, email=acc.email))
