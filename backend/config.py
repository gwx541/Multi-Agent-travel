"""集中读取环境变量。所有模块只通过本文件拿配置，方便切换部署环境。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL as SAURL

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    # LLM Provider 选择：deepseek / openai / azure-openai / ollama
    llm_provider: str

    # 通用 OpenAI 兼容 (deepseek/openai)
    openai_api_key: str
    openai_base_url: str
    openai_model: str
    openai_manager_model: str

    # Azure OpenAI
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_deployment: str
    azure_openai_manager_deployment: str
    azure_openai_api_version: str

    # Ollama（本地）
    ollama_base_url: str
    ollama_model: str
    ollama_manager_model: str

    amap_mcp_url: str
    amap_api_key: str
    amap_js_key: str
    amap_js_security: str
    xhs_mcp_url: str
    train12306_mcp_url: str
    # 酒店 MCP：默认 AIGOHOTEL（魔搭 yorklu/AI_Go_Hotel_MCP），旧 CTRIP_MCP_URL 仍兼容
    hotel_mcp_url: str
    variflight_mcp_url: str

    app_host: str
    app_port: int

    demo_mode: bool

    data_dir: Path

    # 记忆库：未设置 DATABASE_URL 时用 SQLite（data/memory.db）
    database_url: str

    # 鉴权（JWT）；生产务必 AUTH_REQUIRED=true 且设置强随机 JWT_SECRET
    auth_required: bool
    jwt_secret: str
    jwt_expire_minutes: int

    # AUTH_REQUIRED=false 时使用的默认 user_id（单用户模式）。
    # 默认 "demo_user"，与历史前端硬编码的 LEGACY_USER_ID 一致，避免老数据看不到。
    default_user_id: str


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _get_bool(name: str, default: bool = False) -> bool:
    raw = _get(name, "1" if default else "0").lower()
    return raw in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    data_dir = ROOT_DIR / "data"
    data_dir.mkdir(exist_ok=True)

    demo = _get_bool("DEMO_MODE", False)

    # demo 模式下强制清空所有 MCP URL，全部走 mock，无需任何 key
    def _mcp(name: str) -> str:
        return "" if demo else _get(name)

    def _mcp_with_alias(name: str, *aliases: str) -> str:
        """优先取主名；缺失时回退到 alias（用于 ENV 改名后的向后兼容）。"""
        if demo:
            return ""
        v = _get(name)
        if v:
            return v
        for a in aliases:
            v = _get(a)
            if v:
                return v
        return ""

    return Settings(
        llm_provider=_get("LLM_PROVIDER", "deepseek"),
        openai_api_key=_get("OPENAI_API_KEY"),
        openai_base_url=_get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        openai_model=_get("OPENAI_MODEL", "gpt-4o-mini"),
        openai_manager_model=_get("OPENAI_MANAGER_MODEL", "gpt-4o-mini"),
        azure_openai_endpoint=_get("AZURE_OPENAI_ENDPOINT"),
        azure_openai_api_key=_get("AZURE_OPENAI_API_KEY"),
        azure_openai_deployment=_get("AZURE_OPENAI_DEPLOYMENT"),
        azure_openai_manager_deployment=_get("AZURE_OPENAI_MANAGER_DEPLOYMENT"),
        azure_openai_api_version=_get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        ollama_base_url=_get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        ollama_model=_get("OLLAMA_MODEL", "qwen2.5:7b"),
        ollama_manager_model=_get("OLLAMA_MANAGER_MODEL"),
        amap_mcp_url=_mcp("AMAP_MCP_URL"),
        amap_api_key=_get("AMAP_API_KEY"),
        amap_js_key=_get("AMAP_JS_KEY") or _get("AMAP_API_KEY"),
        amap_js_security=_get("AMAP_JS_SECURITY"),
        xhs_mcp_url=_mcp("XHS_MCP_URL"),
        train12306_mcp_url=_mcp("TRAIN12306_MCP_URL"),
        hotel_mcp_url=_mcp_with_alias("HOTEL_MCP_URL", "CTRIP_MCP_URL"),
        variflight_mcp_url=_mcp("VARIFLIGHT_MCP_URL"),
        app_host=_get("APP_HOST", "127.0.0.1"),
        app_port=int(_get("APP_PORT", "8000") or 8000),
        demo_mode=demo,
        data_dir=data_dir,
        database_url=_database_url(data_dir),
        auth_required=_get_bool("AUTH_REQUIRED", False),
        jwt_secret=_get("JWT_SECRET"),
        jwt_expire_minutes=int(_get("JWT_EXPIRE_MINUTES", "10080") or 10080),
        default_user_id=_get("DEFAULT_USER_ID", "demo_user"),
    )


def _database_url(data_dir: Path) -> str:
    raw = _get("DATABASE_URL")
    if raw:
        return raw
    db_path = (data_dir / "memory.db").resolve()
    return SAURL.create(
        drivername="sqlite+aiosqlite",
        database=str(db_path),
    ).render_as_string(hide_password=False)


settings = load_settings()
