"""导航 agent：根据用户当前位置改计划 + 出导航。"""
from __future__ import annotations

from typing import Any

from backend.agents.base import Agent, Tool
from backend.mcp import amap, xhs


async def _reverse(lng: float, lat: float) -> dict[str, Any]:
    return await amap.reverse_geocode(lng, lat)


async def _xhs(keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    return await xhs.search_notes(keyword, limit)


async def _drive(origin: str, destination: str) -> dict[str, Any]:
    return await amap.driving_route(origin, destination)


async def _walk(origin: str, destination: str) -> dict[str, Any]:
    return await amap.walking_route(origin, destination)


async def _transit(
    origin: str, destination: str, city: str = "", city_d: str = ""
) -> dict[str, Any]:
    return await amap.transit_route(origin, destination, city, city_d)


async def _nearby(keyword: str, city: str = "") -> list[dict[str, Any]]:
    return await amap.search_poi(keyword, city)


async def _around(
    lng: float, lat: float, keyword: str = "", radius: int = 1500
) -> list[dict[str, Any]]:
    return await amap.around_search(lng, lat, keyword, radius)


def build_navigation_agent() -> Agent:
    tools = [
        Tool(
            name="amap_reverse_geocode",
            description="把经纬度反查成地址，含 city/district/township/street。",
            parameters={
                "type": "object",
                "properties": {
                    "lng": {"type": "number"},
                    "lat": {"type": "number"},
                },
                "required": ["lng", "lat"],
            },
            handler=_reverse,
        ),
        Tool(
            name="amap_around_search",
            description=(
                "【强烈推荐】按经纬度搜附近 POI，比 amap_search_poi 精准得多。"
                "用于找『附近的地铁站 / 餐厅 / 便利店 / 厕所 / 景点』。"
                "radius 单位米，默认 1500。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "lng": {"type": "number"},
                    "lat": {"type": "number"},
                    "keyword": {"type": "string", "description": "如：地铁站、咖啡、便利店"},
                    "radius": {"type": "integer", "default": 1500},
                },
                "required": ["lng", "lat", "keyword"],
            },
            handler=_around,
        ),
        Tool(
            name="amap_search_poi",
            description="按关键词+城市搜 POI（不知道坐标时用，精度比 around_search 差）。",
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "city": {"type": "string"},
                },
                "required": ["keyword"],
            },
            handler=_nearby,
        ),
        Tool(
            name="amap_direction_transit",
            description=(
                "公交+地铁综合路线（最适合市内出行）。"
                "origin/destination 必须是经纬度 'lng,lat' 字符串；同城时 city=cityd。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "起点 lng,lat"},
                    "destination": {"type": "string", "description": "终点 lng,lat"},
                    "city": {"type": "string", "description": "起点城市，如 广州"},
                    "city_d": {"type": "string", "description": "终点城市"},
                },
                "required": ["origin", "destination", "city"],
            },
            handler=_transit,
        ),
        Tool(
            name="amap_direction_walking",
            description="步行路线，适合 2 公里内的近距离。origin/destination 用 lng,lat。",
            parameters={
                "type": "object",
                "properties": {
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                },
                "required": ["origin", "destination"],
            },
            handler=_walk,
        ),
        Tool(
            name="amap_driving_route",
            description="驾车路线，附 map_url。",
            parameters={
                "type": "object",
                "properties": {
                    "origin": {"type": "string"},
                    "destination": {"type": "string"},
                },
                "required": ["origin", "destination"],
            },
            handler=_drive,
        ),
        Tool(
            name="xhs_search_notes",
            description=(
                "搜小红书笔记，挖『本地人才知道的公共交通 / 隐藏接驳 / 村巴 / 直通车 / 捷径』。"
                "高德给的是官方线路，xhs 用来补充非官方但实用的出行方式。"
                "建议关键词：『<目的地> 怎么去 公共交通』『<目的地> 隐藏路线』"
                "『<出发地> 到 <目的地> 攻略』『<目的地> 公交 接驳』。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["keyword"],
            },
            handler=_xhs,
        ),
    ]

    return Agent(
        name="navigation_agent",
        description="基于用户当前坐标给附近 POI、地铁/步行/驾车路线。",
        system_prompt=(
            "你是『导航 Agent』。用户消息里通常会带 [当前定位] 经纬度 lng,lat 与城市。\n"
            "\n"
            "【第 0 步：先判断目的地是不是『就是用户当前位置』】\n"
            "- 用户说『导航到我现在的地方/当前位置/这里』，或目的地解析后地址、坐标与"
            "[当前定位] 几乎一致（同一精确地址、同名 POI、坐标相距 < 100 米），"
            "**不要查任何路线**，直接友好回答：『你已经在这里了，无需出行～』，"
            "可以追问『要不要看看附近有什么？』，必要时调一次 amap_around_search 给周边推荐；\n"
            "- 同样地，用户没明确指出目的地、只是问『我在哪』，也直接给"
            "amap_reverse_geocode 的地址 + 周边地铁站，**不要查路线**；\n"
            "\n"
            "【第 1 步：有真实出行需求时再走下面的流程】\n"
            "1. 优先用 amap_around_search(lng, lat, keyword) 搜『附近的地铁站 / 公交站 / 餐厅 / 景点』，"
            "比按区名模糊搜要精确得多；\n"
            "2. 市内交通用 amap_direction_transit（公交/地铁综合），不要用 driving；"
            "跨城或自驾才用 amap_driving_route；近距离（< 1.5 公里）用 amap_direction_walking；\n"
            "3. **官方路线给完后必须再调用 xhs_search_notes** 一次，"
            "关键词参考『<目的地> 怎么去 公共交通』『<目的地> 隐藏路线 本地人』，"
            "从笔记里提炼高德可能漏掉的村巴 / 接驳车 / 直通车 / 捷径等本地出行方式；"
            "若 xhs 没有有用线索就不强写本节；\n"
            "4. 输出 markdown（前端会渲染成预览）：\n"
            "   - 主线：### 📍 当前位置 / ### 🎯 推荐去处 / ### 🚇 官方路线（高德）；\n"
            "   - 若 xhs 有补充，再加一段 ### 🌟 本地经验（来自小红书），格式：\n"
            "     `- **要点摘要** —— [笔记标题](笔记 url)`，2-4 条；\n"
            "     笔记标题与 url **必须** 来自 xhs_search_notes 工具返回的 `title` 和 `url` 字段，"
            "禁止自造或拼接其它域名；\n"
            "   - 推荐去处可用 - 列表或 | 表格 |；店名 / 站名加 ** 加粗 **；\n"
            "   - 路线写一段：『从 **XX 站** 乘 5 号线 → 在 **XX** 换乘 3 号线 → 在 **XX** 下车，全程约 X 分钟』；\n"
            "   - 禁止 ![](url) 图片；除小红书笔记 url 外，禁止任何 http/https 网址；\n"
            "5. 不要编造站点 / 路线名，只用工具返回的真实信息。"
        ),
        tools=tools,
    )
