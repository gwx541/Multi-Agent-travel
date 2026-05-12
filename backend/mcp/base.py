"""MCP 通用客户端封装。
统一行为：
- 若给定 URL 走 SSE / Streamable HTTP 真连
- 否则返回 None，由上层切换到 mock
真实 MCP 调用做了懒连接 + 单连接复用，避免每次工具调用都重新握手。"""
from __future__ import annotations

import json as _json
from contextlib import AsyncExitStack
from typing import Any

from backend.observability import span

try:
    from mcp import ClientSession  # type: ignore
    from mcp.client.sse import sse_client  # type: ignore
    from mcp.client.streamable_http import streamablehttp_client  # type: ignore
except Exception:  # pragma: no cover - mcp 没装上时降级
    ClientSession = None  # type: ignore
    sse_client = None  # type: ignore
    streamablehttp_client = None  # type: ignore


def _to_plain(content: Any) -> Any:
    """把 MCP 返回（可能是 list[TextContent|ImageContent|dict|str]）转成 JSON-safe 的 Python 对象。
    TextContent.text 若是合法 JSON 自动 parse，否则保留原文。"""
    if content is None:
        return None
    if isinstance(content, list):
        out: list[Any] = []
        for item in content:
            text = getattr(item, "text", None)
            if text is None and isinstance(item, dict):
                text = item.get("text")
            if isinstance(text, str):
                try:
                    out.append(_json.loads(text))
                except (ValueError, TypeError):
                    out.append(text)
                continue
            if hasattr(item, "model_dump"):
                try:
                    out.append(item.model_dump())
                    continue
                except Exception:
                    pass
            if isinstance(item, dict):
                out.append(item)
            else:
                out.append(str(item))
        return out[0] if len(out) == 1 else out
    if hasattr(content, "model_dump"):
        try:
            return content.model_dump()
        except Exception:
            pass
    if isinstance(content, (dict, str, int, float, bool)):
        return content
    return str(content)


def _flatten_exc(exc: BaseException) -> str:
    """anyio TaskGroup 把子异常打包成 ExceptionGroup，遍历拿到真因。"""
    parts: list[str] = []
    seen: set[int] = set()

    def _walk(e: BaseException) -> None:
        if id(e) in seen:
            return
        seen.add(id(e))
        subs = getattr(e, "exceptions", None)
        if subs:
            for sub in subs:
                _walk(sub)
        else:
            parts.append(f"{type(e).__name__}: {e}")

    _walk(exc)
    return " | ".join(parts) if parts else f"{type(exc).__name__}: {exc}"


class MCPClient:
    """一个 MCP Server 一个实例。每次调用都建立短连接，避免 anyio cancel scope 跨 task 问题。"""

    def __init__(self, name: str, url: str | None) -> None:
        self.name = name
        self.url = url or ""

    @property
    def enabled(self) -> bool:
        return bool(self.url) and ClientSession is not None

    def _is_streamable_http(self) -> bool:
        # /mcp 或 /mcp/ 结尾的视为 Streamable HTTP；其余（如 /sse）走 SSE。
        u = self.url.split("?", 1)[0].rstrip("/")
        return u.endswith("/mcp")

    async def call(self, tool: str, args: dict[str, Any]) -> Any:
        if not self.enabled:
            raise RuntimeError(f"MCP[{self.name}] 未启用")
        with span(
            f"mcp.{self.name}.{tool}",
            **{
                "mcp.server": self.name,
                "mcp.tool": tool,
                "mcp.transport": "streamable_http" if self._is_streamable_http() else "sse",
            },
        ):
            try:
                async with AsyncExitStack() as stack:
                    if self._is_streamable_http():
                        if streamablehttp_client is None:
                            raise RuntimeError("当前 mcp SDK 不支持 streamable HTTP")
                        read, write, _ = await stack.enter_async_context(
                            streamablehttp_client(self.url)
                        )
                    else:
                        read, write = await stack.enter_async_context(sse_client(self.url))
                    session = await stack.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                    result = await session.call_tool(tool, args)
                    return _to_plain(getattr(result, "content", result))
            except BaseException as e:
                detail = _flatten_exc(e)
                print(
                    f"[MCP:{self.name}] call_tool({tool}) 失败: {detail}",
                    flush=True,
                )
                raise RuntimeError(f"[MCP:{self.name}] {tool} 失败: {detail}") from e

    async def aclose(self) -> None:  # 兼容旧调用，不再缓存连接，无需关闭
        return None
