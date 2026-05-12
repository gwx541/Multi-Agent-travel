"""旅行规划 agent：组合小红书 + 高德 + 携程 给出行程。"""
from __future__ import annotations

from typing import Any

from backend.agents.base import Agent, Tool
from backend.mcp import amap, hotel, xhs


async def _xhs(keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    return await xhs.search_notes(keyword, limit)


async def _poi(keyword: str, city: str = "") -> list[dict[str, Any]]:
    return await amap.search_poi(keyword, city)


async def _hotels(
    city: str,
    check_in: str | None = None,
    check_out: str | None = None,
    budget: float | None = None,
) -> list[dict[str, Any]]:
    return await hotel.search_hotels(city, check_in, check_out, budget)


def build_planning_agent() -> Agent:
    tools = [
        Tool(
            name="xhs_search_notes",
            description="搜索小红书旅游攻略帖，返回带封面、链接、点赞数的帖子列表。",
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
        Tool(
            name="amap_search_poi",
            description="按关键词在指定城市搜索景点 / 餐厅 / 商场等 POI，返回名称、评分、地址、配图。",
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "city": {"type": "string", "default": ""},
                },
                "required": ["keyword"],
            },
            handler=_poi,
        ),
        Tool(
            name="ctrip_search_hotels",
            description=(
                "调用酒店 MCP（AIGOHOTEL）查酒店，返回真实预订深链和参考价格。"
                "日期可选：有日期时返回精确价格；无日期时以今天为占位查参考价，"
                "返回字段 _approx_price=True，需在输出中注明『以下为近期参考价格』。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "check_in": {
                        "type": "string",
                        "description": "入住日期 YYYY-MM-DD，可不传",
                    },
                    "check_out": {
                        "type": "string",
                        "description": "退房日期 YYYY-MM-DD，可不传",
                    },
                    "budget": {"type": "number"},
                },
                "required": ["city"],
            },
            handler=_hotels,
        ),
    ]

    return Agent(
        name="planning_agent",
        description="生成详细旅行计划：行程节奏、景点、美食、酒店；并附图片与链接。",
        system_prompt=(
            "你是『旅行规划 Agent』。\n"
            "【输出格式硬性约束】只输出中文 markdown 文本，绝对不要输出 JSON、不要写"
            "`{thought:..., next_agent:..., final_answer:...}` 这种结构、也不要用 ```json``` 围栏；"
            "如果手头工具一时拿不到结果，也要用 markdown 文字告诉用户你尝试了什么、"
            "建议用户补充什么信息，绝不能把内部决策格式吐给用户。\n"
            "【境外目的地特殊规则】如果对话上下文里出现 `[系统注入] 目的地疑似境外`，"
            "请严格按系统注入里的指令执行：禁止调用 amap_search_poi / ctrip_search_hotels，"
            "可调 xhs_search_notes（关键词用中文，例：『冰岛 两日游』），其它内容主要凭你的"
            "知识写。markdown 里要友好说明『国内 MCP 暂未覆盖境外，以下为经验性建议，"
            "酒店/机票请去 Booking、Skyscanner 自行预订』，不要装作查过工具。\n"
            "工作流程（境内目的地，每一步都必须真的调用对应工具，不允许跳过或凭记忆作答）：\n"
            "1. 必须调用 xhs_search_notes 拿 3-5 篇相关攻略；\n"
            "2. 必须调用 amap_search_poi 找具体景点（keyword 用『目的地+景点』，"
            "再单独搜一次『目的地+用户偏好的菜系或美食』）；\n"
            "3. 只要用户说了目的城市，**无论有没有日期都必须调用 ctrip_search_hotels 查酒店**；\n"
            "   ctrip_search_hotels 底层是 AIGOHOTEL，只覆盖中国大陆；\n"
            "   - 有入住/退房日期：正常传 check_in / check_out，返回精确价格；\n"
            "   - 没有日期：只传 city（不传 check_in / check_out），工具会用今天作占位，\n"
            "     返回数据中 _approx_price=True，此时在酒店列表前加一行说明：\n"
            "     『> 💡 以下价格为近期参考报价（非精确价），告诉我入住日期后可查实时报价』；\n"
            "4. 输出 markdown 行程（前端会渲染成预览，不会显示原始符号）：\n"
            "   - 用 ## Day1 / ## Day2 分日，子段用 ### 上午 / ### 下午 / ### 晚上；\n"
            "   - 景点 / 餐厅每条 1-2 行，店名加 ** 加粗 **，可加 ⭐ 评分、📍 地址；\n"
            "   - 可以用表格汇总，例如『| 时间 | 地点 | 备注 |』；表格只能写本节的内容，"
            "**禁止把行程表格放到酒店 / 笔记节标题之下**；\n"
            "   - 节与节之间必须空一整行，下一节标题开始前不能延续上一节的列表 / 表格；\n"
            "   - 推荐酒店：**只有真实调用了 ctrip_search_hotels 并拿到 ≥1 条结果时**才能写"
            "『### 🏨 推荐酒店』，每行格式：\n"
            "     `- [酒店名](酒店 url) ⭐评分 ｜ 价格 / 晚 ｜ 📍地址`，"
            "酒店名与 url **必须**来自工具返回的 `name` / `url` 字段；\n"
            "     **工具没结果时绝对不要输出 🏨 标题**；\n"
            "   - 末尾追加一节 ### 📖 参考小红书笔记（仅当 xhs_search_notes 返回结果时），"
            "格式：`- [笔记标题](笔记 url) —— 一句话摘要`，2-5 条；"
            "title 和 url **必须**来自 xhs_search_notes 工具的 `title` / `url` 字段，禁止自造；\n"
            "   - 禁止 ![](url) 图片；除小红书笔记 url 和携程酒店 url 外，禁止任何 http/https 网址；\n"
            "5. 全部用中文。"
        ),
        tools=tools,
    )
