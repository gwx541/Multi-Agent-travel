"""高德 MCP：定位、POI、导航、驾车路线。
没配 MCP URL 时返回构造好的 mock 数据，保证演示流程不中断。"""
from __future__ import annotations

from typing import Any

from backend.config import settings
from backend.mcp.base import MCPClient

_client = MCPClient("amap", settings.amap_mcp_url)


async def search_poi(keyword: str, city: str = "") -> list[dict[str, Any]]:
    if _client.enabled:
        try:
            raw = await _client.call(
                "maps_text_search", {"keywords": keyword, "city": city}
            )
            return _normalize_poi_list(raw)
        except Exception as e:
            print(f"[amap.search_poi] 走 mock，原因：{type(e).__name__}: {e}")
    return _mock_pois(keyword, city)


async def reverse_geocode(lng: float, lat: float) -> dict[str, Any]:
    if _client.enabled:
        try:
            raw = await _client.call("maps_regeocode", {"location": f"{lng},{lat}"})
            return _normalize_regeo(raw, lng, lat)
        except Exception as e:
            print(f"[amap.reverse_geocode] MCP 失败，尝试 REST API：{type(e).__name__}: {e}")

    # 直接调高德 REST API（不依赖 MCP SSE 连接）
    if settings.amap_api_key:
        try:
            import httpx as _httpx
            url = (
                f"https://restapi.amap.com/v3/geocode/regeo"
                f"?key={settings.amap_api_key}&location={lng},{lat}&extensions=all"
            )
            async with _httpx.AsyncClient(timeout=8) as hc:
                resp = await hc.get(url)
            data = resp.json()
            regeo = (data.get("regeocodes") or data.get("regeocode") or {})
            if isinstance(regeo, list):
                regeo = regeo[0] if regeo else {}
            if regeo:
                return _normalize_regeo(regeo, lng, lat)
        except Exception as e:
            print(f"[amap.reverse_geocode] REST API 也失败：{type(e).__name__}: {e}")

    return {
        "address": f"模拟地址（lng={lng:.4f}, lat={lat:.4f}）",
        "city": "未知城市",
        "district": "未知区",
    }


def _normalize_regeo(raw: Any, lng: float, lat: float) -> dict[str, Any]:
    """高德 MCP 返回常常是 [TextContent(text='{...}')]，统一解析成 dict。"""
    import json as _json

    payload: Any = raw
    if isinstance(raw, list) and raw:
        first = raw[0]
        text = getattr(first, "text", None) or (first.get("text") if isinstance(first, dict) else None)
        if text:
            try:
                payload = _json.loads(text)
            except Exception:
                payload = {"raw": text}
    if not isinstance(payload, dict):
        return {"address": str(payload), "city": "", "district": ""}

    addr_comp = payload.get("addressComponent") or payload.get("address_component") or {}

    def _s(v: Any) -> str:
        if not v:
            return ""
        if isinstance(v, list):
            return v[0] if v else ""
        return str(v)

    province = _s(addr_comp.get("province")) or _s(payload.get("province"))
    city = _s(addr_comp.get("city")) or _s(payload.get("city")) or province
    district = _s(addr_comp.get("district")) or _s(payload.get("district"))
    township = _s(addr_comp.get("township"))
    neighborhood = ""
    nb = addr_comp.get("neighborhood") or {}
    if isinstance(nb, dict):
        neighborhood = _s(nb.get("name"))
    street_obj = addr_comp.get("streetNumber") or {}
    street = ""
    street_number = ""
    if isinstance(street_obj, dict):
        street = _s(street_obj.get("street"))
        street_number = _s(street_obj.get("number"))
    address = (
        payload.get("formatted_address")
        or payload.get("address")
        or f"{province}{city}{district}{township}{street}{street_number}".strip()
        or f"{lng},{lat}"
    )
    return {
        "address": address,
        "province": province,
        "city": city,
        "district": district,
        "township": township,
        "neighborhood": neighborhood,
        "street": street,
        "street_number": street_number,
    }


async def driving_route(origin: str, destination: str) -> dict[str, Any]:
    if _client.enabled:
        try:
            return await _client.call(
                "maps_direction_driving",
                {"origin": origin, "destination": destination},
            )  # type: ignore[return-value]
        except Exception:
            pass
    return {
        "summary": f"自 {origin} 至 {destination}，约 12.4 公里，预计 28 分钟",
        "steps": ["沿当前道路向东 300 米", "右转进入主路 2.1 公里", "到达目的地附近"],
        "map_url": f"https://uri.amap.com/navigation?from={origin}&to={destination}&mode=car",
    }


async def walking_route(origin: str, destination: str) -> dict[str, Any]:
    if _client.enabled:
        try:
            return await _client.call(
                "maps_direction_walking",
                {"origin": origin, "destination": destination},
            )  # type: ignore[return-value]
        except Exception:
            pass
    return {
        "summary": f"自 {origin} 至 {destination}，步行约 800 米，预计 12 分钟",
        "map_url": f"https://uri.amap.com/navigation?from={origin}&to={destination}&mode=walk",
    }


async def transit_route(
    origin: str, destination: str, city: str = "", city_d: str = ""
) -> dict[str, Any]:
    """公交/地铁综合路线。origin/destination 必须是经纬度 'lng,lat'。"""
    if _client.enabled:
        try:
            args: dict[str, Any] = {"origin": origin, "destination": destination}
            if city:
                args["city"] = city
            if city_d:
                args["cityd"] = city_d
            return await _client.call(
                "maps_direction_transit_integrated", args
            )  # type: ignore[return-value]
        except Exception:
            pass
    return {
        "summary": "公交综合路线 mock：地铁 5 号线 → 换乘 1 号线 → 步行 200 米到达",
        "map_url": f"https://uri.amap.com/navigation?from={origin}&to={destination}&mode=bus",
    }


async def geocode(address: str, city: str = "") -> dict[str, Any]:
    """地理编码：address → {location: 'lng,lat', ...}。"""
    if not address:
        return {}
    if _client.enabled:
        try:
            args: dict[str, Any] = {"address": address}
            if city:
                args["city"] = city
            raw = await _client.call("maps_geo", args)
            return _normalize_geo(raw)
        except Exception as e:
            print(f"[amap.geocode] 走 mock，原因：{type(e).__name__}: {e}")
    return {}


def _normalize_geo(raw: Any) -> dict[str, Any]:
    """高德 maps_geo 返回多种壳：{results: [...]}, {return: [...]}, {geocodes: [...]}, list 等。"""
    candidates: list[Any] = []
    keys = ("results", "return", "geocodes", "data")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                for k in keys:
                    if item.get(k):
                        candidates.extend(item[k])
                        break
        if not candidates:
            candidates = [x for x in raw if isinstance(x, dict)]
    elif isinstance(raw, dict):
        for k in keys:
            if raw.get(k):
                candidates = raw[k]
                break
        if not candidates and raw.get("location"):
            candidates = [raw]
    for c in candidates:
        if isinstance(c, dict) and c.get("location"):
            return c
    return {}


async def around_search(
    lng: float, lat: float, keyword: str = "", radius: int = 1500
) -> list[dict[str, Any]]:
    """按经纬度搜附近 POI（地铁站、餐厅、便利店等）。"""
    if _client.enabled:
        try:
            raw = await _client.call(
                "maps_around_search",
                {
                    "location": f"{lng},{lat}",
                    "keywords": keyword,
                    "radius": str(radius),
                },
            )
            return _normalize_poi_list(raw)
        except Exception as e:
            print(f"[amap.around_search] 走 mock，原因：{type(e).__name__}: {e}")
    return _mock_pois(keyword, "")


def _normalize_poi_list(raw: Any) -> list[dict[str, Any]]:
    """高德 around/text_search 可能返回 list[dict] 或 {'pois': [...]}，统一成 list。"""
    if isinstance(raw, list):
        if raw and isinstance(raw[0], dict) and "pois" in raw[0]:
            return raw[0].get("pois") or []
        return raw
    if isinstance(raw, dict):
        return raw.get("pois") or raw.get("data") or []
    return []


def _mock_pois(keyword: str, city: str) -> list[dict[str, Any]]:
    sample = [
        {
            "name": f"{city or '本地'}·{keyword}人气店 A",
            "address": "示例区示例路 1 号",
            "rating": 4.7,
            "photo": "https://picsum.photos/seed/a/600/400",
            "url": "https://www.amap.com/",
        },
        {
            "name": f"{city or '本地'}·{keyword}口碑店 B",
            "address": "示例区滨江路 88 号",
            "rating": 4.6,
            "photo": "https://picsum.photos/seed/b/600/400",
            "url": "https://www.amap.com/",
        },
        {
            "name": f"{city or '本地'}·{keyword}小众宝藏 C",
            "address": "示例区文创园 7 栋",
            "rating": 4.8,
            "photo": "https://picsum.photos/seed/c/600/400",
            "url": "https://www.amap.com/",
        },
    ]
    return sample
