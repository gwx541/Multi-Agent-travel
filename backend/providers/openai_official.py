"""官方 OpenAI provider。

复用同一组 OPENAI_* 变量（OPENAI_API_KEY / OPENAI_MODEL），
但 base_url 默认走官方，model 默认 gpt-4o-mini。
"""
from __future__ import annotations

from openai import AsyncOpenAI

from backend.config import settings
from backend.providers import LLMSession


def build() -> LLMSession:
    return LLMSession(
        client=AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or "https://api.openai.com/v1",
        ),
        model=settings.openai_model or "gpt-4o-mini",
        manager_model=settings.openai_manager_model or "gpt-4o-mini",
        provider="openai",
    )
