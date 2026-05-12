"""搜索 agent：交通工具（机票走飞常准 + 火车走 12306）+ 机场天气。"""
from __future__ import annotations

from typing import Any

from backend.agents.base import Agent, Tool
from backend.mcp import train12306, variflight


async def _flights(
    from_city: str, to_city: str, date: str, budget: float | None = None
) -> list[dict[str, Any]]:
    return await variflight.search_flights(from_city, to_city, date, budget)


async def _trains(from_city: str, to_city: str, date: str) -> list[dict[str, Any]]:
    return await train12306.query_trains(from_city, to_city, date)


async def _weather(airport: str) -> dict[str, Any]:
    return await variflight.get_airport_weather(airport)


def build_search_agent() -> Agent:
    tools = [
        Tool(
            name="variflight_search_flights",
            description=(
                "用飞常准查机票：传出发城市、到达城市（中文或 IATA 代码均可，如 北京/BJS）、"
                "日期 YYYY-MM-DD，可选预算上限。返回航班 + 价格 + 订票链接。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "from_city": {"type": "string"},
                    "to_city": {"type": "string"},
                    "date": {"type": "string"},
                    "budget": {"type": "number"},
                },
                "required": ["from_city", "to_city", "date"],
            },
            handler=_flights,
        ),
        Tool(
            name="train12306_query",
            description="查询 12306 火车 / 高铁班次。",
            parameters={
                "type": "object",
                "properties": {
                    "from_city": {"type": "string"},
                    "to_city": {"type": "string"},
                    "date": {"type": "string"},
                },
                "required": ["from_city", "to_city", "date"],
            },
            handler=_trains,
        ),
        Tool(
            name="variflight_airport_weather",
            description="查机场未来 3 天天气，airport 传 IATA 代码（如 PEK / CTU）。",
            parameters={
                "type": "object",
                "properties": {
                    "airport": {"type": "string"},
                },
                "required": ["airport"],
            },
            handler=_weather,
        ),
    ]

    return Agent(
        name="search_agent",
        description="查机票（飞常准）、火车票（12306）、机场天气。",
        system_prompt=(
            "你是『搜索 Agent』，专门查交通：\n"
            "【境外目的地特殊规则】如果对话上下文里出现 `[系统注入] 目的地疑似境外`，"
            "禁止调用 variflight_search_flights 与 train12306_query（它们只覆盖中国大陆，"
            "调了会空跑）。直接用 markdown 回复：建议用户前往 Skyscanner / 谷歌航班 / "
            "携程国际版 自行查机票，并提供一些一般性建议（航司、签证、提前订票时间等）。\n"
            "1. 解析用户的出发地 / 目的地 / 日期 / 预算；\n"
            "2. 同时调用机票（variflight_search_flights）和火车（train12306_query），"
            "除非用户明确指定一种；\n"
            "3. 如果用户关心是否准点 / 取消，可以加查 variflight_airport_weather；\n"
            "4. 输出 markdown（前端会渲染成预览）：\n"
            "   - 用 ### ✈️ 机票 / ### 🚄 火车 分两段；\n"
            "   - 每段用 markdown 表格汇总：『| 航班/车次 | 时刻 | 价格 | 备注 |』；\n"
            "   - 火车的『车次』列必须写成 `[车次号](车次 url)` 形式，"
            "url **必须**来自 train12306_query 工具返回的 `url` 字段，禁止自造；\n"
            "   - 机票同理，可用 `[航班号](订票 url)` 引用 variflight_search_flights 返回的 url；\n"
            "   - 除上述工具返回的 12306 / 携程 / 飞常准 url 外，禁止任何其它 http/https 网址；\n"
            "5. 没有日期就回复『请告诉我出发日期』，不要瞎编。"
        ),
        tools=tools,
    )
