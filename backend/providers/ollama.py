"""Ollama provider（本地 LLM，OpenAI 兼容 /v1 端点）。

环境变量：
- OLLAMA_BASE_URL   默认 http://localhost:11434/v1
- OLLAMA_MODEL      默认 qwen2.5:7b （需事先 `ollama pull`）

注意：
1. Ollama /v1 是兼容 OpenAI 但 API_KEY 可以随便填，本地认证不校验
2. 不少 7B 模型 function calling 表现一般，复杂工具调用可能失败
"""
from __future__ import annotations

from openai import AsyncOpenAI

from backend.config import settings
from backend.providers import LLMSession


def build() -> LLMSession:
    base = (settings.ollama_base_url or "http://localhost:11434/v1").rstrip("/")
    model = settings.ollama_model or "qwen2.5:7b"
    manager_model = settings.ollama_manager_model or model
    return LLMSession(
        client=AsyncOpenAI(api_key="ollama", base_url=base),
        model=model,
        manager_model=manager_model,
        provider="ollama",
    )
