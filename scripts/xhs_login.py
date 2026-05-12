"""一次性脚本：扫码登录 xpzouying/xiaohongshu-mcp。
流程：
1. 调用 get_login_qrcode 拿到 base64 PNG，保存到当前目录 xhs_qrcode.png 并打开
2. 用手机小红书 App 扫码
3. 轮询 check_login_status，登录成功后退出，cookies 持久化在容器 /app/data
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = os.getenv("XHS_MCP_URL", "http://localhost:18060/mcp")
# 默认保存到 data/ 下，docker-compose 把它 mount 到主机 ./data，方便宿主机直接打开扫码
_default_dir = Path(os.getenv("XHS_QR_DIR", "/app/data" if Path("/app/data").is_dir() else "."))
QR_PATH = _default_dir / "xhs_qrcode.png"


def _extract_text(content) -> str:
    if isinstance(content, list):
        out = []
        for item in content:
            t = getattr(item, "text", None) or (item.get("text") if isinstance(item, dict) else None)
            if t:
                out.append(t)
        return "\n".join(out)
    return str(content)


def _extract_image_b64(content) -> str | None:
    """优先识别 MCP ImageContent；兼容 dict 形态。"""
    if not isinstance(content, list):
        content = [content]
    for item in content:
        type_ = getattr(item, "type", None)
        if type_ is None and isinstance(item, dict):
            type_ = item.get("type")
        if type_ == "image":
            data = getattr(item, "data", None)
            if data is None and isinstance(item, dict):
                data = item.get("data")
            if isinstance(data, str) and len(data) > 100:
                return data
        text = getattr(item, "text", None) or (item.get("text") if isinstance(item, dict) else None)
        if isinstance(text, str):
            m = re.search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]+)", text)
            if m:
                return m.group(1)
    return None


def _save_qrcode(content) -> Path | None:
    b64 = _extract_image_b64(content)
    if not b64:
        return None
    QR_PATH.write_bytes(base64.b64decode(b64))
    return QR_PATH


async def main() -> int:
    async with streamablehttp_client(URL) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            names = {t.name for t in tools.tools}
            print(f"已发现 {len(names)} 个工具，登录相关: " +
                  ", ".join(n for n in names if "login" in n.lower() or "qr" in n.lower()))

            res = await s.call_tool("check_login_status", {})
            text = _extract_text(res.content)
            print("[check] " + text[:200])
            if any(kw in text for kw in ("已登录", "logged_in\":true", '"login":true', "true")):
                if "false" not in text.lower():
                    print("✅ cookies 已存在，无需扫码")
                    return 0

            print("\n获取登录二维码…")
            res = await s.call_tool("get_login_qrcode", {})
            text = _extract_text(res.content)
            print("[hint] " + text[:120])
            saved = _save_qrcode(res.content)
            if not saved:
                print("⚠️ 未识别到二维码图片字段，content 类型一览：")
                for i, item in enumerate(res.content if isinstance(res.content, list) else [res.content]):
                    t = getattr(item, "type", "?")
                    print(f"  [{i}] type={t}, attrs={[a for a in dir(item) if not a.startswith('_')][:8]}")
                return 1
            print(f"二维码已保存：{saved}")
            try:
                os.startfile(str(saved))
            except Exception:
                pass
            print("\n👉 请在 60 秒内用手机小红书 App 扫码登录…\n")

            for i in range(30):
                await asyncio.sleep(2)
                try:
                    res = await s.call_tool("check_login_status", {})
                    text = _extract_text(res.content)
                except Exception as e:
                    print(f"[{i}] 检查异常: {e}")
                    continue
                if any(kw in text for kw in ("已登录", '"login":true', '"logged_in":true')):
                    print(f"\n✅ 登录成功（第 {i+1} 次轮询）")
                    print(text[:300])
                    return 0
                print(f"[{i+1}/30] 仍未登录…")
            print("⏰ 超时仍未检测到登录，请重试。")
            return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
