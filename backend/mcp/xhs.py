"""小红书 MCP：搜索旅游攻略贴。
推荐对接 xpzouying/xiaohongshu-mcp（streamable HTTP, 默认 http://localhost:18060/mcp）。
工具名是 search_feeds；返回字段含 title/cover/nickname/url/feed_id/xsec_token。
没接 MCP 时回 mock，链接走小红书真实搜索页。"""
from __future__ import annotations

from typing import Any

from backend.config import settings
from backend.mcp.base import MCPClient

_client = MCPClient("xhs", settings.xhs_mcp_url)


async def search_notes(keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    if _client.enabled:
        try:
            raw = await _client.call("search_feeds", {"keyword": keyword})
            normalized = _normalize_feeds(raw, limit)
            if normalized:
                return normalized
        except Exception as e:
            print(f"[xhs.search_notes] 走 mock，原因：{type(e).__name__}: {e}", flush=True)
    return _mock_notes(keyword, limit)


def _normalize_feeds(raw: Any, limit: int) -> list[dict[str, Any]]:
    """xpzouying/xiaohongshu-mcp 的 search_feeds 返回结构：
    {feeds:[{id, xsecToken, noteCard:{displayTitle, user:{nickname}, interactInfo:{likedCount},
             cover:{urlDefault|urlPre|url}}}]}
    """
    if raw is None:
        return []
    items: Any = raw
    if isinstance(raw, dict):
        for key in ("feeds", "notes", "data", "items", "list", "result"):
            if isinstance(raw.get(key), list):
                items = raw[key]
                break
    if not isinstance(items, list):
        return []

    def _g(d: Any, *keys: str, default: Any = None) -> Any:
        for k in keys:
            if isinstance(d, dict) and k in d and d[k] not in (None, ""):
                return d[k]
        return default

    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        note_card = it.get("noteCard") or it.get("note_card") or {}
        feed_id = _g(it, "id", "feed_id", "note_id", default="")
        xsec = _g(it, "xsecToken", "xsec_token", default="")

        title = _g(note_card, "displayTitle", "display_title", "title") or _g(it, "title", "desc") or "(无标题)"
        user = note_card.get("user") or {}
        author = _g(user, "nickname", "nickName", "name") or _g(it, "nickname", "author", default="")
        interact = note_card.get("interactInfo") or note_card.get("interact_info") or {}
        likes_raw = _g(interact, "likedCount", "liked_count", "likes") or _g(it, "liked_count", "likes", default=0)
        try:
            likes = int(str(likes_raw).replace(",", "")) if likes_raw else 0
        except (TypeError, ValueError):
            likes = 0
        cover_obj = note_card.get("cover") or {}
        cover = (
            _g(cover_obj, "urlDefault", "urlPre", "url")
            or _g(it, "cover", "image", "thumb", default="")
        )
        if isinstance(cover, dict):
            cover = _g(cover, "urlDefault", "urlPre", "url", default="")

        url = it.get("url") or it.get("note_url")
        if not url and feed_id:
            url = f"https://www.xiaohongshu.com/explore/{feed_id}"
            if xsec:
                from urllib.parse import quote
                url += f"?xsec_token={quote(xsec)}&xsec_source=pc_search"

        out.append(
            {
                "title": title,
                "author": author,
                "likes": likes,
                "cover": cover or "",
                "url": url or "https://www.xiaohongshu.com/",
                "summary": _g(note_card, "desc", "summary") or _g(it, "desc", "summary", default=""),
            }
        )
        if len(out) >= limit:
            break
    return out


def _mock_notes(keyword: str, limit: int) -> list[dict[str, Any]]:
    """没接真实小红书 MCP 时的兜底。
    URL 改为小红书真实搜索页，点进去能看到该关键词的真实笔记。"""
    from urllib.parse import quote

    q = quote(keyword)
    search_url = f"https://www.xiaohongshu.com/search_result?keyword={q}&source=web_search_result_notes"
    presets = [
        ("3 天 2 晚保姆级攻略", "小薯条", 12345, "包含详细行程、避坑、人均预算约 1200。"),
        ("小众路线｜5 个出片机位", "胶片旅人", 8902, "出片率拉满，附拍摄时段与穿搭。"),
        ("美食合集｜从早餐吃到夜宵", "干饭少女", 15670, "12 家亲测好吃的，附人均与地址。"),
        ("亲子游攻略｜带娃轻松版", "麻麻爱旅行", 6789, "适合 3-8 岁的行程节奏。"),
        ("穷游 VS 精致游对比", "理性消费者", 4321, "两种预算两种体验。"),
    ]
    out = []
    for i, (suffix, author, likes, summary) in enumerate(presets[:limit]):
        out.append(
            {
                "title": f"{keyword} {suffix}",
                "author": author,
                "likes": likes,
                "cover": f"https://picsum.photos/seed/xhs{i}/400/500",
                "url": search_url,
                "summary": summary,
            }
        )
    return out
