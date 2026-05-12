"""12306 MCP：火车 / 高铁查询。
推荐对接 Joooook/12306-mcp（streamable HTTP，本地启动：
    npx -y 12306-mcp --port 8088
然后把 .env 里的 TRAIN12306_MCP_URL 设为 http://127.0.0.1:8088/mcp）。
工具：get-tickets，参数 {date, fromStation, toStation, format:"json"}，
返回 list[{train_no, start_train_code, start_time, arrive_time, lishi, prices,
           from_station, to_station, from_station_telecode, to_station_telecode}]。
没接 MCP 时回 mock。"""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from backend.config import settings
from backend.mcp.base import MCPClient

_client = MCPClient("12306", settings.train12306_mcp_url)


_SEAT_KEYS = {
    "second_class": ("二等座", "二等"),
    "first_class": ("一等座", "一等"),
    "business": ("商务座", "特等座"),
    "soft_sleeper": ("软卧", "高级软卧", "动卧"),
    "hard_sleeper": ("硬卧",),
    "no_seat": ("无座",),
}


async def query_trains(
    from_city: str, to_city: str, date: str
) -> list[dict[str, Any]]:
    if _client.enabled:
        try:
            raw = await _client.call(
                "get-tickets",
                {
                    "date": date,
                    "fromStation": from_city,
                    "toStation": to_city,
                    "format": "json",
                },
            )
            normalized = _normalize_tickets(raw, date)
            if normalized:
                return normalized
        except Exception as e:
            print(
                f"[12306.query_trains] 走 mock，原因：{type(e).__name__}: {e}",
                flush=True,
            )
    return _mock_trains(from_city, to_city, date)


def _build_purchase_url(
    from_name: str, from_code: str, to_name: str, to_code: str, date: str
) -> str:
    """拼 12306 余票真实查询页 URL，点进去能看到对应车次列表。"""
    fs = quote(f"{from_name},{from_code}", safe=",")
    ts = quote(f"{to_name},{to_code}", safe=",")
    return (
        "https://kyfw.12306.cn/otn/leftTicket/init?"
        f"linktypeid=dc&fs={fs}&ts={ts}&date={date}&flag=N,N,Y"
    )


def _pick_price(prices: list[dict[str, Any]], aliases: tuple[str, ...]) -> Any:
    for p in prices:
        name = str(p.get("seat_name") or "")
        if any(a in name for a in aliases):
            try:
                price = float(p.get("price") or 0)
            except (TypeError, ValueError):
                price = 0
            num = str(p.get("num") or "").strip()
            return {"price": price, "num": num}
    return None


def _normalize_tickets(raw: Any, date: str) -> list[dict[str, Any]]:
    items: Any = raw
    if isinstance(raw, dict):
        for k in ("data", "tickets", "result", "items", "list"):
            if isinstance(raw.get(k), list):
                items = raw[k]
                break
    if isinstance(items, str):
        # mcp 偶尔会返回纯文本表格，无法稳健解析；交回 mock。
        return []
    if not isinstance(items, list):
        return []

    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        train_code = str(it.get("start_train_code") or it.get("train_no") or "")
        if not train_code:
            continue
        start_time = str(it.get("start_time") or "")
        arrive_time = str(it.get("arrive_time") or "")
        lishi = str(it.get("lishi") or "")
        from_name = str(it.get("from_station") or "")
        to_name = str(it.get("to_station") or "")
        from_code = str(it.get("from_station_telecode") or "")
        to_code = str(it.get("to_station_telecode") or "")
        prices = it.get("prices") if isinstance(it.get("prices"), list) else []

        seats: dict[str, Any] = {}
        for key, aliases in _SEAT_KEYS.items():
            seats[key] = _pick_price(prices, aliases)

        url = _build_purchase_url(from_name, from_code, to_name, to_code, date)
        out.append(
            {
                "train_no": train_code,
                "depart": f"{from_name} {start_time}",
                "arrive": f"{to_name} {arrive_time}",
                "duration": lishi,
                "second_class": (seats.get("second_class") or {}).get("price"),
                "first_class": (seats.get("first_class") or {}).get("price"),
                "business": (seats.get("business") or {}).get("price"),
                "seats": seats,
                "url": url,
            }
        )
    return out


def _mock_trains(from_city: str, to_city: str, date: str) -> list[dict[str, Any]]:
    url = (
        "https://kyfw.12306.cn/otn/leftTicket/init?"
        f"linktypeid=dc&fs={quote(from_city)}&ts={quote(to_city)}&date={date}&flag=N,N,Y"
    )
    return [
        {"train_no": "G1234", "depart": f"{from_city} 08:30", "arrive": f"{to_city} 12:05",
         "duration": "3h35m", "second_class": 553.5, "first_class": 884.5, "url": url},
        {"train_no": "G5678", "depart": f"{from_city} 13:10", "arrive": f"{to_city} 16:42",
         "duration": "3h32m", "second_class": 553.5, "first_class": 884.5, "url": url},
        {"train_no": "D2233", "depart": f"{from_city} 17:48", "arrive": f"{to_city} 22:30",
         "duration": "4h42m", "second_class": 312.0, "first_class": 498.0, "url": url},
    ]
