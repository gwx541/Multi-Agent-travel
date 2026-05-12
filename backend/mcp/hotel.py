"""酒店 MCP（默认 AIGOHOTEL：魔搭 yorklu/AI_Go_Hotel_MCP）。

对外入口 `search_hotels(city, check_in, check_out, budget)`，已切换到 AIGOHOTEL 协议：
- 工具: `searchHotels`
- 参数: place / placeType / checkInParam / size / starRatings / hotelTags / originQuery
- 返回: hotelId / name / address / starRating / bookingUrl / imageUrl / price / latitude / longitude / ...

环境变量优先 `HOTEL_MCP_URL`；缺失时回退 `CTRIP_MCP_URL`（旧字段名兼容）。
申请 ModelScope SSE 端点：https://www.modelscope.cn/mcp/servers/yorklu/AI_Go_Hotel_MCP

> 旧引用入口 `backend.mcp.ctrip` 仍保留为 shim，转发到本模块；
> 新代码请直接 `from backend.mcp import hotel`。
"""
from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import quote

from backend.config import settings
from backend.mcp.base import MCPClient

_client = MCPClient("hotel", settings.hotel_mcp_url)


# ---- mock 兜底用的城市 ID 表（仅 fallback URL 用）-------------------------------
_CITY_IDS: dict[str, int] = {
    "北京": 1, "上海": 2, "天津": 3, "重庆": 4,
    "济南": 5, "沈阳": 6, "西安": 7, "青岛": 8, "长春": 9, "哈尔滨": 10,
    "南通": 11, "南京": 12, "无锡": 13, "苏州": 14, "常州": 15, "扬州": 16,
    "杭州": 17, "嘉兴": 18, "宁波": 19, "温州": 20, "绍兴": 21,
    "舟山": 22, "金华": 23, "台州": 24,
    "厦门": 25, "大连": 26, "太原": 27, "成都": 28,
    "深圳": 30, "广州": 32, "珠海": 33,
    "海口": 38, "三亚": 39,
    "长沙": 206, "武汉": 477, "郑州": 199,
    "昆明": 232, "贵阳": 270, "南宁": 280,
    "兰州": 231, "银川": 281, "乌鲁木齐": 311,
    "西宁": 250, "拉萨": 246,
    "石家庄": 233, "合肥": 31, "南昌": 209,
}


def _normalize_city(city: str) -> str:
    s = (city or "").strip()
    for suf in ("市", "州市", "省"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return s


def _nights(check_in: str, check_out: str) -> int:
    try:
        ci = date.fromisoformat(check_in)
        co = date.fromisoformat(check_out)
        return max(1, (co - ci).days)
    except Exception:
        return 1


def _is_ctrip_hotel_detail(url: str) -> bool:
    u = url.lower()
    if "hoteldetail" in u or "hotelinfo" in u:
        return True
    if "/hotels/detail" in u or "hotels/detail?" in u:
        return True
    if "hotelid=" in u and ("ctrip.com" in u or "trip.com" in u):
        return True
    return False


def _hotel_url(city: str, hotel_name: str, check_in: str, check_out: str) -> str:
    """仅 mock 路径会用到的兜底 URL，尽量锁定到城市页 + 关键字。"""
    name_kw = (hotel_name or "").strip()
    keyword = name_kw if name_kw else _normalize_city(city)
    city_id = _CITY_IDS.get(_normalize_city(city))
    if city_id is not None:
        return (
            "https://hotels.ctrip.com/hotels/list?"
            f"city={city_id}&keyword={quote(keyword)}"
            f"&checkIn={check_in}&checkOut={check_out}"
        )
    fallback_kw = f"{_normalize_city(city)} {name_kw}".strip()
    return (
        "https://hotels.ctrip.com/hotels/list?"
        f"keyword={quote(fallback_kw)}"
        f"&checkIn={check_in}&checkOut={check_out}"
    )


# ---- AIGOHOTEL 返回归一化 -----------------------------------------------------
def _flatten(raw: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for sub in raw:
            if isinstance(sub, list):
                items.extend(x for x in sub if isinstance(x, dict))
            elif isinstance(sub, dict):
                items.append(sub)
    elif isinstance(raw, dict):
        for key in (
            "hotelInformationList",   # AIGOHOTEL searchHotels
            "hotels", "data", "results", "list", "items",
        ):
            v = raw.get(key)
            if isinstance(v, list):
                items.extend(x for x in v if isinstance(x, dict))
                break
        else:
            items = [raw]
    return items


def _normalize_aigohotel(
    raw: Any, city: str, check_in: str, check_out: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in _flatten(raw):
        name = (
            it.get("name")
            or it.get("hotelName")
            or it.get("title")
            or "未知酒店"
        )
        price = (
            it.get("price")
            or it.get("lowestPrice")
            or it.get("minPrice")
        )
        # AIGOHOTEL: price 是 {hasPrice, lowestPrice, currency, message}
        if isinstance(price, dict):
            price = (
                price.get("lowestPrice")
                or price.get("amount")
                or price.get("value")
            )
        rating = (
            it.get("starRating")
            or it.get("rating")
            or it.get("score")
        )
        address = it.get("address") or it.get("location") or ""
        photo = (
            it.get("imageUrl")
            or it.get("image")
            or it.get("photo")
            or it.get("cover")
            or ""
        )
        url = it.get("bookingUrl") or it.get("url") or ""
        if not url:
            url = _hotel_url(city, name, check_in, check_out)
        out.append(
            {
                "name": name,
                "price": price if price is not None else "—",
                "rating": rating if rating is not None else "—",
                "address": address,
                "photo": photo,
                "url": url,
                "hotelId": it.get("hotelId") or it.get("id"),
                "currency": it.get("currency"),
                "latitude": it.get("latitude") or it.get("lat"),
                "longitude": it.get("longitude") or it.get("lng"),
                "amenities": it.get("hotelAmenities") or it.get("amenities") or [],
                "tags": it.get("tags") or [],
                "description": it.get("description") or "",
                "raw": it,
            }
        )
    return out


# ---- 对外入口（与旧版签名兼容）-----------------------------------------------
async def search_hotels(
    city: str,
    check_in: str | None = None,
    check_out: str | None = None,
    budget: float | None = None,
) -> list[dict[str, Any]]:
    """查询酒店。

    ``check_in`` / ``check_out`` 可省略——缺失时使用今天 / 明天作为占位，
    拿到的 price 为当前参考价，返回数据里会带 ``_approx_price=True`` 标记，
    供上层 agent 在回复中说明"以下为参考报价"。
    """
    from datetime import date as _date
    from backend.utils.locale import detect_overseas

    # 日期兜底
    approx = False
    if not check_in or not check_out:
        approx = True
        today = _date.today()
        check_in = check_in or today.isoformat()
        check_out = check_out or (_date.fromordinal(today.toordinal() + 1)).isoformat()

    # AIGOHOTEL 当前只覆盖中国大陆，境外城市直接短路返回，附带 _note 让 agent 解释。
    overseas = detect_overseas(city or "")
    if overseas:
        return [
            {
                "_unsupported_region": overseas,
                "_note": (
                    f"酒店 MCP（AIGOHOTEL）当前不覆盖境外目的地『{overseas}』，"
                    "无任何酒店候选。请在 markdown 回复里说明该限制，并建议用户去 "
                    "Booking / Agoda / Airbnb 自行预订；不要硬编酒店。"
                ),
            }
        ]

    if _client.enabled:
        place = _normalize_city(city) or city
        origin_query = (
            f"在{place}找{check_in}入住到{check_out}的酒店"
        )
        if budget:
            origin_query += f"，预算每晚不超过{int(budget)}元"

        args: dict[str, Any] = {
            "originQuery": origin_query,
            "place": place,
            "placeType": "城市",
            "countryCode": "CN",
            "size": 10,
            "checkInParam": {
                "checkInDate": check_in,
                "stayNights": _nights(check_in, check_out),
                "adultCount": 2,
            },
        }
        if budget:
            args["hotelTags"] = {"maxPricePerNight": float(budget)}
        try:
            raw = await _client.call("searchHotels", args)
            normalized = _normalize_aigohotel(raw, city, check_in, check_out)
            if normalized:
                if approx:
                    for h in normalized:
                        h["_approx_price"] = True
                if budget:
                    priced = [
                        h for h in normalized
                        if isinstance(h.get("price"), (int, float)) and h["price"] <= budget
                    ]
                    if priced:
                        return priced[:10]
                return normalized[:10]
        except Exception as e:
            print(f"[hotel.search_hotels] AIGOHOTEL 失败，走 mock：{type(e).__name__}: {e}", flush=True)

    # ---- mock 兜底：保留之前的样例数据 + 关键字搜索 URL --------------------
    hotels = [
        {
            "name": f"{city} 万豪酒店",
            "price": 920,
            "rating": 4.8,
            "address": "市中心商圈",
            "photo": "https://picsum.photos/seed/h1/600/400",
        },
        {
            "name": f"{city} 亚朵 S",
            "price": 568,
            "rating": 4.7,
            "address": "地铁口 200 米",
            "photo": "https://picsum.photos/seed/h2/600/400",
        },
        {
            "name": f"{city} 城市便捷",
            "price": 268,
            "rating": 4.5,
            "address": "靠近老城区",
            "photo": "https://picsum.photos/seed/h3/600/400",
        },
    ]
    for h in hotels:
        h["url"] = _hotel_url(city, h["name"], check_in, check_out)
        if approx:
            h["_approx_price"] = True
    if budget:
        hotels = [h for h in hotels if h["price"] <= budget] or hotels
    return hotels


# 向后兼容名：旧测试或外部调用可能仍引用
_ensure_hotel_urls = _normalize_aigohotel  # noqa: E305
