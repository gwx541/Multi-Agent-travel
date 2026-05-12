"""Azure OpenAI provider。

环境变量：
- AZURE_OPENAI_ENDPOINT       例：https://your-resource.openai.azure.com/
- AZURE_OPENAI_API_KEY
- AZURE_OPENAI_DEPLOYMENT      用作 model 名（Azure 是按 deployment 调）
- AZURE_OPENAI_MANAGER_DEPLOYMENT  可选；不填则跟主 deployment 一致
- AZURE_OPENAI_API_VERSION    默认 2024-10-21
"""
from __future__ import annotations

from openai import AsyncAzureOpenAI

from backend.config import settings
from backend.providers import LLMSession


def build() -> LLMSession:
    endpoint = settings.azure_openai_endpoint
    api_key = settings.azure_openai_api_key
    deployment = settings.azure_openai_deployment
    if not (endpoint and api_key and deployment):
        raise RuntimeError(
            "Azure OpenAI 缺配置：请设置 AZURE_OPENAI_ENDPOINT / "
            "AZURE_OPENAI_API_KEY / AZURE_OPENAI_DEPLOYMENT"
        )
    return LLMSession(
        client=AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=settings.azure_openai_api_version or "2024-10-21",
        ),
        model=deployment,
        manager_model=settings.azure_openai_manager_deployment or deployment,
        provider="azure-openai",
    )
