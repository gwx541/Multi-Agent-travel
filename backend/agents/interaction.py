"""用户交互 agent：理解 + 澄清 + 把偏好写进记忆。"""
from __future__ import annotations

from typing import Any

from backend.agents.base import Agent, Tool
from backend.memory.memory_store import memory_store
from backend.memory.short_term import short_term_memory


async def _save_pref(user_id: str, preference: str) -> dict[str, Any]:
    await memory_store.add_preference(user_id, preference)
    return {"ok": True, "saved": preference}


async def _save_session_note(conversation_id: str, note: str) -> dict[str, Any]:
    short_term_memory.add_note(conversation_id, note)
    return {"ok": True, "saved": note}


def build_interaction_agent(user_id: str, conversation_id: str | None = None) -> Agent:
    save_pref_tool = Tool(
        name="save_user_preference",
        description=(
            "【长期记忆】将用户的长期偏好永久保存（跨对话有效），"
            "如饮食禁忌、住宿偏好、出行风格等。"
            "示例：『不吃辣』『偏好亲子友好酒店』『喜欢小众景点』。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "preference": {
                    "type": "string",
                    "description": "一条简洁的偏好陈述，比如『不吃辣』『偏好亲子友好酒店』",
                }
            },
            "required": ["preference"],
        },
        handler=lambda preference: _save_pref(user_id, preference),
    )

    save_session_tool = Tool(
        name="save_session_context",
        description=(
            "【短期记忆】将本次会话的关键信息记录为便签（仅本次会话有效，服务重启后消失）。"
            "适合记录：出行人数/同行人组成、本次出发日期、当前规划目的地、预算范围等。"
            "示例：『3人出行含1名儿童』『出发日期：5月17日』『目的地：成都』。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "一条简洁的会话上下文便签",
                }
            },
            "required": ["note"],
        },
        handler=lambda note: _save_session_note(conversation_id or "", note),
    )

    tools = [save_pref_tool]
    if conversation_id:
        tools.append(save_session_tool)

    return Agent(
        name="interaction_agent",
        description="负责理解用户输入、澄清模糊需求、识别并保存用户偏好。",
        system_prompt=(
            "你是『小旅』——一个多智能体协同的中文旅行助手对话入口（不是一个独立 Agent）。\n"
            "对用户而言你就是『小旅』整体，不要把内部分工暴露给用户。\n"
            "\n"
            "整体能力（要让用户知道这些都能帮）：\n"
            "- 行程规划：景点、餐厅、酒店、按天排日程；\n"
            "- 出行导航：基于定位推荐附近 POI、地铁/步行/驾车路线、本地经验；\n"
            "- 票务搜索：机票（飞常准）、火车（12306）、机场天气；\n"
            "- 长期偏好记忆：记住饮食、住宿、风格偏好（跨对话永久保存）；\n"
            "- 短期会话记忆：记住本次对话的关键信息（出行人数、日期、目的地等）。\n"
            "\n"
            "你这一步要做的事：\n"
            "1. 自我介绍 / 闲聊 / 澄清模糊需求时由你出面，用 1-3 句中文友好作答；\n"
            "2. 如果用户给的关键信息缺失（出发地/目的地/时间/预算/同行人/偏好），"
            "主动澄清，每次最多问 2 个最关键的点；\n"
            "3. 用户透露长期偏好（如『不吃辣』『喜欢小众』）时调用 save_user_preference 保存；\n"
            "4. 用户提到本次行程关键信息（出行人数、出发日期、目的地、预算等）时，"
            "调用 save_session_context 记为会话便签，方便后续 agent 引用；\n"
            "5. 真要执行行程规划/查交通/查导航时，**不要在这一步亲自规划**，"
            "只需用一句话告诉用户『马上为你规划』即可，后台会自动接力；"
            "千万不要说『我不能规划』『那是别人的活儿』之类自贬能力的话。\n"
            "\n"
            "硬性约束（避免幻觉，重要）：\n"
            "- 只能基于本轮『用户消息』的内容回答；\n"
            "- 严禁编造用户没明确说过的事实，例如『你之前在 X 玩过』『你去年去过 Y』，"
            "即便 subtask 里提到了某些地名也不能说成用户的亲历；\n"
            "- 用户已保存的长期偏好可以引用，但要用『记得你提过…』而不是『你之前去过…』；\n"
            "- 禁止任何链接和 http/https 网址；除非必要不要用 markdown 标题和表格。"
        ),
        tools=tools,
    )
