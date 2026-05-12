"""DeepSeek provider（OpenAI 兼容协议）。

复用现有的 OPENAI_* 环境变量，保持向后兼容：
- OPENAI_API_KEY  / OPENAI_BASE_URL（默认 https://api.deepseek.com/v1）
- OPENAI_MODEL    / OPENAI_MANAGER_MODEL（默认 deepseek-chat）
"""
from __future__ import annotations

from openai import AsyncOpenAI

from backend.config import settings
from backend.providers import LLMSession


def build() -> LLMSession:
    return LLMSession(
        client=AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or "https://api.deepseek.com/v1",
        ),
        model=settings.openai_model or "deepseek-chat",
        manager_model=settings.openai_manager_model or "deepseek-chat",
        provider="deepseek",
    )
