"""飞常准 MCP（Variflight）：查机票 + 航班行程。
官方文档：https://github.com/variflight/variflight-mcp
ModelScope SSE 端点：https://mcp.api-inference.modelscope.net/<token>/sse

工具优先级（拿到带价格的最完整数据）：
1. searchFlightItineraries —— 含可购航班 + 价格
2. searchFlightsByDepArr  —— 直飞航班，价格可能没有
3. mock                    —— 完全没配置或调用失败时兜底
"""
from __future__ import annotations

from typing import Any

from backend.config import settings
from backend.mcp.base import MCPClient

_client = MCPClient("variflight", settings.variflight_mcp_url)

# 中文城市名 → 飞常准用的 IATA 城市代码（最常用的几个，未命中时原样传）
_CITY_TO_IATA: dict[str, str] = {
    "北京": "BJS", "上海": "SHA", "广州": "CAN", "深圳": "SZX",
    "成都": "CTU", "重庆": "CKG", "杭州": "HGH", "南京": "NKG",
    "武汉": "WUH", "西安": "SIA", "长沙": "CSX", "厦门": "XMN",
    "青岛": "TAO", "昆明": "KMG", "三亚": "SYX", "海口": "HAK",
    "天津": "TSN", "郑州": "CGO", "济南": "TNA", "沈阳": "SHE",
    "大连": "DLC", "哈尔滨": "HRB", "长春": "CGQ", "福州": "FOC",
    "南昌": "KHN", "合肥": "HFE", "南宁": "NNG", "贵阳": "KWE",
    "兰州": "LHW", "乌鲁木齐": "URC", "拉萨": "LXA", "呼和浩特": "HET",
    "香港": "HKG", "澳门": "MFM", "台北": "TPE",
}


def _to_city_code(city: str) -> str:
    if not city:
        return city
    city = city.strip()
    if city in _CITY_TO_IATA:
        return _CITY_TO_IATA[city]
    for k, v in _CITY_TO_IATA.items():
        if k in city:
            return v
    return city.upper()


def _normalize(items: Any) -> list[dict[str, Any]]:
    """把飞常准返回的多种结构归一成统一卡片字段。"""
    if items is None:
        return []
    if isinstance(items, dict):
        for key in ("flights", "itineraries", "data", "results", "list"):
            if key in items and isinstance(items[key], list):
                items = items[key]
                break
        else:
            items = [items]
    if not isinstance(items, list):
        return []

    out: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        airline = (
            it.get("airline")
            or it.get("airlineName")
            or it.get("carrier")
            or it.get("flightNo")
            or it.get("fnum")
            or "未知航班"
        )
        flight_no = it.get("flightNo") or it.get("fnum") or it.get("flight_number")
        if flight_no and flight_no not in str(airline):
            airline = f"{airline} {flight_no}"

        dep_time = (
            it.get("depTime")
            or it.get("departureTime")
            or it.get("dep_time")
            or it.get("planDepTime")
            or ""
        )
        arr_time = (
            it.get("arrTime")
            or it.get("arrivalTime")
            or it.get("arr_time")
            or it.get("planArrTime")
            or ""
        )
        dep_city = it.get("depCity") or it.get("dep") or it.get("from") or ""
        arr_city = it.get("arrCity") or it.get("arr") or it.get("to") or ""
        depart = f"{dep_city} {dep_time}".strip()
        arrive = f"{arr_city} {arr_time}".strip()

        price = (
            it.get("price")
            or it.get("lowestPrice")
            or it.get("minPrice")
            or it.get("cheapestPrice")
        )
        if isinstance(price, dict):
            price = price.get("amount") or price.get("value")

        url = it.get("url") or it.get("bookUrl") or "https://www.variflight.com/"

        out.append(
            {
                "airline": airline,
                "depart": depart or "—",
                "arrive": arrive or "—",
                "price": price if price is not None else "—",
                "url": url,
                "raw": it,
            }
        )
    return out


async def search_flights(
    from_city: str, to_city: str, date: str, budget: float | None = None
) -> list[dict[str, Any]]:
    dep = _to_city_code(from_city)
    arr = _to_city_code(to_city)

    if _client.enabled:
        for tool, args in (
            (
                "searchFlightItineraries",
                {"depCityCode": dep, "arrCityCode": arr, "depDate": date},
            ),
            (
                "getFlightPriceByCities",
                {"dep_city": dep, "arr_city": arr, "dep_date": date},
            ),
            (
                "searchFlightsByDepArr",
                {"dep": dep, "arr": arr, "date": date},
            ),
        ):
            try:
                raw = await _client.call(tool, args)
                normalized = _normalize(raw)
                if normalized:
                    if budget is not None:
                        priced = [
                            f for f in normalized
                            if isinstance(f["price"], (int, float)) and f["price"] <= budget
                        ]
                        if priced:
                            return priced
                    return normalized
            except Exception:
                continue

    return _mock(from_city, to_city, budget)


async def get_airport_weather(airport: str) -> dict[str, Any]:
    if _client.enabled:
        try:
            return await _client.call(
                "getFutureWeatherByAirport", {"airport": airport.upper()}
            )  # type: ignore[return-value]
        except Exception:
            pass
    return {
        "airport": airport.upper(),
        "forecast": [
            {"date": "Day1", "weather": "晴", "temp": "18~26℃"},
            {"date": "Day2", "weather": "多云", "temp": "17~24℃"},
            {"date": "Day3", "weather": "小雨", "temp": "15~21℃"},
        ],
    }


def _mock(from_city: str, to_city: str, budget: float | None) -> list[dict[str, Any]]:
    flights = [
        {
            "airline": "国航 CA1234",
            "depart": f"{from_city} 07:25",
            "arrive": f"{to_city} 10:05",
            "price": 880,
            "url": "https://www.variflight.com/",
        },
        {
            "airline": "东航 MU5678",
            "depart": f"{from_city} 12:40",
            "arrive": f"{to_city} 15:20",
            "price": 720,
            "url": "https://www.variflight.com/",
        },
        {
            "airline": "南航 CZ4321",
            "depart": f"{from_city} 19:10",
            "arrive": f"{to_city} 21:55",
            "price": 590,
            "url": "https://www.variflight.com/",
        },
    ]
    if budget:
        flights = [f for f in flights if f["price"] <= budget] or flights
    return flights
