"""向后兼容 shim：原模块已改名为 backend.mcp.hotel。

历史代码可能通过 `from backend.mcp import ctrip` 或 `from backend.mcp.ctrip import ...`
拿酒店搜索能力，这里把符号原样转发到 hotel 模块；新代码请用 hotel 模块。
"""
from __future__ import annotations

import warnings as _warnings

from backend.mcp.hotel import *  # noqa: F401,F403 - 显式向后兼容
from backend.mcp import hotel as _hotel

_warnings.warn(
    "backend.mcp.ctrip 已改名为 backend.mcp.hotel，请迁移引用。",
    DeprecationWarning,
    stacklevel=2,
)

search_hotels = _hotel.search_hotels  # 主入口，签名不变
