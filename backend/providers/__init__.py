"""LLM Provider 工厂。

按 settings.llm_provider 选不同的客户端构造器，对外只暴露：
- get_session() -> LLMSession(client, model, manager_model)

四个 provider 都返回 OpenAI 兼容客户端（AsyncOpenAI / AsyncAzureOpenAI），
让 backend/agents/base.py 与 backend/orchestrator.py 的 chat.completions.create 调用
完全统一，不必为 provider 写分支。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.config import settings


@dataclass
class LLMSession:
    """主体业务代码只用这三个字段。"""

    client: Any  # AsyncOpenAI | AsyncAzureOpenAI
    model: str
    manager_model: str
    provider: str


_session: LLMSession | None = None


def get_session() -> LLMSession:
    global _session
    if _session is None:
        _session = _build()
    return _session


def _build() -> LLMSession:
    provider = (settings.llm_provider or "deepseek").strip().lower()
    if provider == "deepseek":
        from backend.providers.deepseek import build as _b
    elif provider == "openai":
        from backend.providers.openai_official import build as _b
    elif provider == "azure-openai":
        from backend.providers.azure_openai import build as _b
    elif provider in ("ollama", "ollama-models"):
        from backend.providers.ollama import build as _b
    else:
        raise ValueError(
            f"未知 LLM_PROVIDER={provider!r}，"
            "可选：deepseek / openai / azure-openai / ollama"
        )
    return _b()
