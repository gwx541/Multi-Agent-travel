"""主持人编排（Microsoft Agent Framework Magentic 思路的轻量实现）。

每一步：
  manager LLM 看当前对话+候选 agent，决定 next_agent / 给它的子任务 / 是否结束。
  执行该 agent，把结果加入对话上下文，再回到 manager。
最多 N 步，避免死循环。
所有阶段都通过 async generator 把事件 yield 出去，方便 SSE 推到前端。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, AsyncIterator

from openai import AsyncOpenAI

from backend.agents.base import Agent, get_openai
from backend.observability import set_attr, span
from backend.providers import get_session
from backend.agents.interaction import build_interaction_agent
from backend.agents.navigation import build_navigation_agent
from backend.agents.planning import build_planning_agent
from backend.agents.search import build_search_agent
from backend.agents.testing import build_testing_agent
from backend.config import settings
from backend.memory.memory_store import memory_store
from backend.memory.short_term import short_term_memory
from backend.mcp import amap
from backend.utils.locale import detect_overseas

MAX_STEPS = 8

# 极简闲聊匹配：完全无旅行意图 / 短问候时跳过 manager 决策，直接交 interaction_agent 一次出答案
_CHITCHAT_RE = re.compile(
    r"^[\s\W]*(你好|您好|hello|hi|hey|嗨|嘿|在吗|早|早安|晚安|"
    r"谢谢|多谢|再见|拜拜|bye|ok|好的|嗯+|哈+|哦+|测试|test)[\s\W]*$",
    re.IGNORECASE,
)
# 自我介绍类：能做什么、你是谁、你叫啥…直接走交互 agent 一次出答案
_SELF_INTRO_RE = re.compile(
    r"(你是谁|你叫(什么|啥)|你是什么|介绍(一)?下(你)?自己|"
    r"你能做什么|你会做什么|你能干(什么|啥)|你都能(干|做)什么|"
    r"你有什么(功能|本事|能力)|你的功能)",
)


def _is_chitchat(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    if len(text) <= 30 and _CHITCHAT_RE.match(text):
        return True
    if len(text) <= 40 and _SELF_INTRO_RE.search(text):
        return True
    return False


@dataclass
class Event:
    type: str
    payload: dict[str, Any]

    def to_sse(self) -> dict[str, Any]:
        return {"event": self.type, "data": json.dumps(self.payload, ensure_ascii=False)}


def _build_agents(
    user_id: str, conversation_id: str | None = None
) -> dict[str, Agent]:
    return {
        "interaction_agent": build_interaction_agent(user_id, conversation_id),
        "planning_agent": build_planning_agent(),
        "navigation_agent": build_navigation_agent(),
        "search_agent": build_search_agent(),
        "testing_agent": build_testing_agent(),
    }


def _agents_brief(agents: dict[str, Agent]) -> str:
    return "\n".join(f"- {name}: {a.description}" for name, a in agents.items())


_MANAGER_SYSTEM = """你是一个 Multi-Agent 旅行助手的『主持人』。
你不直接回答用户，而是从下列候选 agent 中挑下一个该行动的 agent，并告诉它该做什么。
候选 agent：
{agents}

【各 agent 拥有的真实工具，不要凭空否认能力】
- interaction_agent: save_user_preference（只用来保存用户长期偏好）
- planning_agent: xhs_search_notes（小红书攻略搜索）、amap_search_poi（高德 POI 景点/餐厅）、
                  ctrip_search_hotels（酒店搜索，AIGOHOTEL MCP）
- navigation_agent: amap_reverse_geocode、amap_around_search（按坐标搜附近，最精准）、
                    amap_direction_transit（地铁/公交综合）、amap_direction_walking、
                    amap_driving_route、amap_search_poi、
                    xhs_search_notes（用来补充本地人才知道的非官方公交 / 村巴 / 直通车）
- search_agent: variflight_search_flights（机票）、train12306_query（火车）、variflight_airport_weather
- testing_agent: 仅做最终质检

每一步严格输出 JSON（不要 markdown 围栏）：
{{
  "thought": "你的简短思考",
  "next_agent": "agent 名 或 'final'",
  "subtask": "给该 agent 的明确子任务（user_id, 上下文已自动注入，不必复述）",
  "final_answer": "若 next_agent=='final'，把要发给用户的最终回复放这里；否则留空"
}}

【写 subtask 时的硬约束（避免下游 agent 幻觉用户经历）】
- subtask 只能描述『现在要做什么』，不能把历史里出现过的地名/活动复述成用户的亲历，
  例如禁止写『用户曾去过永州』『用户上次咨询过 X』；如确实需要让 agent 知道历史
  问过某地，必须明确写成『用户上一轮咨询过永州攻略』而不是『用户去过永州』；
- 若本轮用户只是闲聊 / 自我介绍，subtask 简短交代即可，不要塞任何历史地名/事件。

规则：
- **只有当用户输入完全没有目的地、没有日期、没有任何旅行动作意图（纯打招呼/纯客套）时**，才用 interaction_agent；
- 用户提到目的地（任何城市名）、攻略、行程、景点、美食、酒店、推荐等关键词 → 直接派给 planning_agent；
- 用户提到『小红书』『xhs』『攻略』『笔记』等 → 必走 planning_agent（它有 xhs_search_notes 工具）；
- 用户提到『附近』『这边』『周围』『我现在在的地方』等词，并且系统已注入 location，
  优先 navigation_agent，让它基于用户经纬度/城市来回答；
- 临时改路线 / 提供经纬度 → navigation_agent；
- 查机票 / 火车 → search_agent；
- planning/search/navigation 跑完一次后，可让 testing_agent 质检一次；如果 PASS 就结束；
- 最多 {max_steps} 步，到达上限请直接 final。

【关键：何时 final】
- interaction_agent 跑完一次后，如果它已经给出了对用户友好的回复（问候 / 澄清问题 / 给选项），
  直接 next_agent='final'，把它那段 text 原样放进 final_answer，不要再让任何 agent 重复回答；
- 同一个 agent 不要连续调用两次产生几乎相同的输出；
- 用户只是闲聊（如"你好""谢谢"），interaction_agent 回复一次后立刻 final；
- planning_agent / navigation_agent / search_agent 任一跑完一次并产出了带链接/卡片的完整回复，
  就直接 next_agent='final'，把它那段 text 原样复制到 final_answer，不要再换 agent 重写一遍。
  只有当回复明显不完整或工具全部失败时，才允许重新调用同一个 agent；
- 总的来说：一轮对话内的 agent 调用尽量控制在 1~2 次，能 final 就 final。"""


def _manager_messages(
    agents: dict[str, Agent],
    user_input: str,
    history: list[dict[str, Any]],
    transcript: list[dict[str, Any]],
    session_notes: str = "",
) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": _MANAGER_SYSTEM.format(
                agents=_agents_brief(agents), max_steps=MAX_STEPS
            ),
        }
    ]
    # 短期记忆：会话便签（由 interaction_agent 在本次对话中提取保存）
    if session_notes:
        msgs.append({"role": "system", "content": session_notes})
    # 对话历史：优先用短期缓存（更多条），回退到 DB 的最近 8 条
    if history:
        joined = "\n".join(f"{h['role']}: {h['content']}" for h in history)
        msgs.append({"role": "system", "content": "近期对话：\n" + joined})
    msgs.append({"role": "user", "content": "本轮用户输入：" + user_input})
    if transcript:
        log = "\n".join(
            f"[{step['agent']}] {step['summary']}" for step in transcript
        )
        msgs.append({"role": "system", "content": "本轮已发生：\n" + log})
    return msgs


_MANAGER_LIKE_KEYS = {"next_agent", "final_answer", "subtask", "thought"}


def _sanitize_agent_text(text: str) -> str:
    """Agent 偶发退化成 manager-style JSON 输出（DeepSeek 在多轮 json_object 上下文里会
    模仿格式）。这里识别出来后剥成 final_answer / thought，避免把决策 JSON 当回答展示。
    """
    if not text:
        return text
    raw = text.strip()
    candidate = raw
    fence = re.match(r"```(?:json)?\s*(.+?)\s*```\s*$", raw, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()
    if not (candidate.startswith("{") and candidate.endswith("}")):
        return text
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        return text
    if not isinstance(obj, dict):
        return text
    if not (set(obj.keys()) & _MANAGER_LIKE_KEYS):
        return text
    inner = (obj.get("final_answer") or "").strip()
    if inner:
        return inner
    hint = (obj.get("thought") or obj.get("subtask") or "").strip()
    return (
        "抱歉，本轮工具没拿到足够材料，无法给出靠谱的答复。"
        + (f"\n\n（内部线索：{hint}）" if hint else "")
        + "\n\n建议再补充一下目的地国家 / 城市、时间、预算等关键信息再试一次～"
    )


_TITLE_SYSTEM = (
    "你是一个对话标题生成器。基于给定的『用户首条提问』和『助手回复摘要』，"
    "生成一个 4–12 字的中文短标题，概括会话主题。\n"
    "硬性要求：只输出标题本身，不带任何引号、标点（含书名号 / 顿号）、emoji、前后缀、"
    "解释；不要『关于』『讨论』等模板词；如内容是问候 / 闲聊，输出『闲聊』。"
)
_TITLE_MAX_CHARS = 12


def _generate_conversation_title(user_input: str) -> str | None:
    """从用户首条输入截取标题，不调 LLM，零网络依赖。"""
    raw = re.sub(r"\s+", " ", (user_input or "").strip())
    raw = raw.lstrip("？！?! \u3000")
    if not raw:
        return None
    return raw[:_TITLE_MAX_CHARS].rstrip()


async def _maybe_auto_title(
    client: AsyncOpenAI,
    user_id: str,
    conversation_id: str | None,
    user_input: str,
    assistant_text: str,
) -> str | None:
    """如果会话还没标题，让 LLM 起一个 4–12 字的中文短标题，写库并返回；否则返回 None。"""
    if not conversation_id:
        return None
    try:
        if not await memory_store.needs_auto_title(user_id, conversation_id):
            return None
        title = _generate_conversation_title(user_input)
        if not title:
            return None
        await memory_store.update_conversation(user_id, conversation_id, title=title)
        return title
    except Exception as e:
        print(f"[title] auto-title skipped: {type(e).__name__}: {e}")
        return None


_HOTEL_HEADING_RE = re.compile(r"(?:^|\n)#{1,6}\s*🏨[^\n]*\n")
_HOTEL_ITEM_RE = re.compile(r"^\s*-\s*\[[^\]]+\]\(https?://", re.MULTILINE)
_ANY_HEADING_RE = re.compile(r"\n#{1,6}\s")


def _strip_orphan_hotel_section(text: str) -> str:
    """删除『🏨 推荐酒店』孤立标题——下面没有真实酒店链接条目时整段抠掉。

    判定 "真实酒店条目" = 章节内出现至少一行 ``- [...](https?://...`` 的 markdown 链接列表。
    其它情况（行程表格漏进来 / 普通段落 / 空）都判为孤立标题，整段删除到下个 ``#`` 标题前。
    """
    if not text:
        return text
    out: list[str] = []
    cursor = 0
    for m in _HOTEL_HEADING_RE.finditer(text):
        out.append(text[cursor : m.start()])
        body_start = m.end()
        nxt = _ANY_HEADING_RE.search(text, body_start)
        body_end = nxt.start() + 1 if nxt else len(text)
        body = text[body_start:body_end]
        if _HOTEL_ITEM_RE.search(body):
            # 合法酒店区块，连标题一起保留
            out.append(text[m.start():body_end])
        else:
            # 孤立标题：标题及其下方非酒店内容全部抠掉，保留一个换行避免上下连接
            out.append("\n")
        cursor = body_end
    out.append(text[cursor:])
    return "".join(out)


def _extract_decision(raw: str) -> dict[str, Any] | None:
    """容错解析 manager 返回的 JSON。
    DeepSeek 在 json_object 模式下偶尔会双层包裹 / 加 ```json 围栏，需要兜底。"""
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and ("next_agent" in obj or "final_answer" in obj):
            return obj
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*(.+?)\s*```", raw, re.DOTALL)
    if fence:
        try:
            obj = json.loads(fence.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    for start in (i for i, c in enumerate(raw) if c == "{"):
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(raw[start : i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(obj, dict) and (
                        "next_agent" in obj or "final_answer" in obj
                    ):
                        return obj
                    break
    return None


async def _ask_manager(
    client: AsyncOpenAI,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    sess = get_session()
    with span(
        "manager.decide",
        **{"llm.model": sess.manager_model, "llm.provider": sess.provider},
    ):
        resp = await client.chat.completions.create(
            model=sess.manager_model,
            messages=messages,
            response_format={"type": "json_object"},
        )
    raw = resp.choices[0].message.content or "{}"
    parsed = _extract_decision(raw)
    if parsed is None:
        return {
            "thought": "JSON 解析失败，直接 final",
            "next_agent": "final",
            "subtask": "",
            "final_answer": raw,
        }
    return parsed


async def run_orchestration(
    user_id: str,
    user_input: str,
    location: dict[str, float] | None = None,
    skip_user_persist: bool = False,
    conversation_id: str | None = None,
) -> AsyncIterator[Event]:
    """主入口：以事件流形式驱动一轮多 agent 协作。

    ``skip_user_persist=True`` 用于"编辑历史用户消息并重新生成"场景：
    用户消息已由路由层就地替换到历史中，本函数不再重复 append。
    ``conversation_id`` 指定属于哪个会话；省略时取该用户最新会话（或自动新建）。
    """
    with span(
        "orchestrator.run",
        **{
            "user.id": user_id,
            "user.has_location": bool(location),
            "user_input.length": len(user_input or ""),
            "user_input.preview": (user_input or "")[:80],
            "conversation.id": conversation_id or "",
        },
    ):
        async for ev in _run_orchestration_inner(
            user_id,
            user_input,
            location,
            skip_user_persist=skip_user_persist,
            conversation_id=conversation_id,
        ):
            yield ev


async def _run_orchestration_inner(
    user_id: str,
    user_input: str,
    location: dict[str, float] | None = None,
    skip_user_persist: bool = False,
    conversation_id: str | None = None,
) -> AsyncIterator[Event]:
    client = get_openai()

    user_blob = await memory_store.get_user(user_id, conversation_id)
    # 取到的会话 id（若入参为 None，这里就是最新会话；用户没有会话时返回 None）
    conversation_id = user_blob.get("conversation_id") or conversation_id

    agents = _build_agents(user_id, conversation_id)

    # 短期记忆：优先用进程内缓存（当前 runtime 会话，最多 20 条）
    # 回退：DB 里最近 8 条（跨重启恢复上下文）
    st_messages = (
        short_term_memory.get_messages(conversation_id)[-20:]
        if conversation_id
        else []
    )
    db_history = user_blob.get("history", [])
    history = st_messages if st_messages else db_history[-8:]

    pref_summary = await memory_store.summary_for_prompt(user_id, conversation_id)
    user_msg_id: int | None = None
    if not skip_user_persist:
        user_msg_id = await memory_store.append_history(
            user_id, "user", user_input, conversation_id=conversation_id
        )
        # 同步到短期缓存
        if conversation_id:
            short_term_memory.append_message(conversation_id, "user", user_input)

    enriched_input = user_input
    location_info: dict[str, Any] | None = None
    nearby_landmarks: list[dict[str, Any]] = []
    if location:
        try:
            location_info = await amap.reverse_geocode(
                float(location.get("lng")), float(location.get("lat"))
            )
        except Exception:
            location_info = None
        # 主动搜一圈附近的地铁站，作为最强精度参考点（PC 浏览器定位误差 1-3 km）
        try:
            nearby_landmarks = await amap.around_search(
                float(location.get("lng")),
                float(location.get("lat")),
                keyword="地铁站",
                radius=2000,
            ) or []
        except Exception:
            nearby_landmarks = []

        loc_text = ""
        if location_info:
            loc_text = (
                f"{location_info.get('city','')} {location_info.get('district','')} "
                f"{location_info.get('township','')} "
                f"{location_info.get('neighborhood','')} "
                f"{location_info.get('street','')}{location_info.get('street_number','')}"
            ).strip()

        landmarks_text = ""
        if nearby_landmarks:
            top = nearby_landmarks[:5]
            landmarks_text = "；".join(
                (p.get("name") or "") for p in top if isinstance(p, dict) and p.get("name")
            )

        enriched_input += (
            f"\n[系统注入] 用户当前定位: lng={location.get('lng')}, "
            f"lat={location.get('lat')}"
            + (f"\n精确地址：{loc_text}" if loc_text else "")
            + (f"\n附近最近地铁站（按距离排序）：{landmarks_text}" if landmarks_text else "")
        )

    overseas_dst = detect_overseas(user_input)
    if overseas_dst:
        enriched_input += (
            f"\n[系统注入] 目的地疑似境外（{overseas_dst}）。当前接入的国内向 MCP 都"
            "不覆盖境外，请遵守以下规则：\n"
            "- 禁止调用 amap_search_poi / amap_geo / amap_around / ctrip_search_hotels / "
            "12306_search_tickets / variflight_search_flights（这些只覆盖中国大陆，"
            "调了也会空跑或返回错乱数据）；\n"
            "- 仍可调用 xhs_search_notes，关键词请用中文（例如『冰岛 两日游』）；\n"
            "- 行程主要凭 LLM 自身知识 + 小红书攻略产出 markdown，给出景点 / 美食 / "
            "天气 / 签证 / 交通 建议；\n"
            "- 机票请在 markdown 里提示用户去 Skyscanner / 谷歌航班 / 携程国际版 自行搜，"
            "酒店请提示用户去 Booking / Agoda / Airbnb 自行预订；\n"
            "- 末尾要明确告知『当前境外目的地暂不支持工具实时查价，仅提供经验性建议』。"
        )

    yield Event(
        "manager",
        {
            "msg": "已收到请求，开始调度",
            "preference": pref_summary,
            "location": location,
            "location_info": location_info,
        },
    )

    final_answer = ""
    if _is_chitchat(user_input):
        agent = agents["interaction_agent"]
        yield Event("agent_start", {"agent": agent.name, "subtask": "闲聊快速通道"})
        try:
            result = await agent.run(
                enriched_input,
                extra_context=f"用户ID: {user_id}\n{pref_summary}",
            )
            text = result.get("text", "").strip() or "嗨～有什么可以帮你的？"
        except Exception as e:
            text = f"（闲聊通道异常：{type(e).__name__}: {e}）"
        yield Event("agent_end", {"agent": agent.name, "text": text, "tool_results": []})
        assistant_msg_id = await memory_store.append_history(
            user_id, "assistant", text, conversation_id=conversation_id
        )
        if conversation_id is None:
            # 若入参为 None，append_history 内部会自动建一个 conversation；取回最新
            conversation_id = (
                await memory_store.get_user(user_id)
            ).get("conversation_id")
        # 同步 assistant 回复到短期缓存
        if conversation_id:
            short_term_memory.append_message(conversation_id, "assistant", text)
        conv_title = await _maybe_auto_title(
            client, user_id, conversation_id, user_input, text
        )
        yield Event(
            "final",
            {
                "text": text,
                "conversation_id": conversation_id,
                "conversation_title": conv_title,
                "message_ids": {
                    "user": user_msg_id,
                    "assistant": assistant_msg_id,
                },
            },
        )
        return

    session_notes = short_term_memory.notes_summary(conversation_id) if conversation_id else ""

    collected_pois: list[dict[str, Any]] = []
    try:
        async for ev in _run_loop(client, agents, enriched_input, history, pref_summary, session_notes, location, location_info, nearby_landmarks, user_id):
            if ev.type == "_final":
                final_answer = ev.payload["text"]
                collected_pois = ev.payload.get("pois", [])
            else:
                yield ev
                if ev.type == "agent_end":
                    _harvest_pois(ev.payload.get("tool_results") or [], collected_pois)
    except Exception as e:  # 把后端异常显式回传，避免前端只看到 SSE 中断
        msg = f"后端异常：{type(e).__name__}: {e}"
        yield Event("error", {"text": msg})
        final_answer = msg

    if not final_answer.strip():
        final_answer = "（无最终回复）"

    if collected_pois:
        city = (location_info or {}).get("city", "")
        try:
            await _enrich_poi_locations(collected_pois, city)
        except Exception as e:
            print(f"[poi geocode] 跳过补全：{type(e).__name__}: {e}")

    final_answer = _strip_orphan_hotel_section(final_answer)

    assistant_msg_id = await memory_store.append_history(
        user_id, "assistant", final_answer, conversation_id=conversation_id
    )
    if conversation_id is None:
        conversation_id = (
            await memory_store.get_user(user_id)
        ).get("conversation_id")
    # 同步 assistant 回复到短期缓存
    if conversation_id:
        short_term_memory.append_message(conversation_id, "assistant", final_answer)
    conv_title = await _maybe_auto_title(
        client, user_id, conversation_id, user_input, final_answer
    )
    yield Event(
        "final",
        {
            "text": final_answer,
            "pois": collected_pois,
            "location": location,
            "location_info": location_info,
            "conversation_id": conversation_id,
            "conversation_title": conv_title,
            "message_ids": {
                "user": user_msg_id,
                "assistant": assistant_msg_id,
            },
        },
    )


async def _enrich_poi_locations(pois: list[dict[str, Any]], city: str) -> None:
    """对没有 location 的 POI 调 amap.geocode 补坐标，并发 4，最多处理前 12 个。"""
    import asyncio
    import re as _re

    targets = [p for p in pois[:12] if not p.get("location") and p.get("name")]
    if not targets:
        return
    sem = asyncio.Semaphore(4)

    def _strip(name: str) -> str:
        # 去掉中英括号内容，例如 "肯德基(广州商学院店)" -> "肯德基"
        return _re.sub(r"[（(][^)）]*[)）]", "", name).strip() or name

    async def _try(addr: str) -> str:
        if not addr:
            return ""
        try:
            geo = await amap.geocode(addr, city)
            loc = geo.get("location") if isinstance(geo, dict) else ""
            return loc if isinstance(loc, str) and "," in loc else ""
        except Exception:
            return ""

    async def one(p: dict[str, Any]) -> None:
        async with sem:
            name = p["name"]
            stripped = _strip(name)
            attempts: list[str] = []
            if p.get("address"):
                attempts.append(f"{stripped} {p['address']}")
            attempts.append(stripped)
            if p.get("address"):
                attempts.append(p["address"])
            for addr in attempts:
                loc = await _try(addr)
                if loc:
                    p["location"] = loc
                    return

    await asyncio.gather(*[one(p) for p in targets])


_POI_TOOLS = {"amap_search_poi", "amap_around_search"}


def _harvest_pois(tool_results: list[dict[str, Any]], bucket: list[dict[str, Any]]) -> None:
    """从一组 tool_results 里抽取 amap POI（带 name），按 name+address 去重塞入 bucket。"""
    existing = {(p.get("name", ""), p.get("address", "")) for p in bucket}
    for tr in tool_results:
        if not isinstance(tr, dict):
            continue
        tool_name = tr.get("tool")
        if tool_name not in _POI_TOOLS:
            continue
        data = tr.get("data")
        items = data if isinstance(data, list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or ""
            if not name:
                continue
            key = (name, item.get("address", ""))
            if key in existing:
                continue
            existing.add(key)
            bucket.append(
                {
                    "name": name,
                    "address": item.get("address", ""),
                    "location": item.get("location", ""),
                    "typecode": item.get("typecode", ""),
                    "photo": item.get("photo") or "",
                }
            )


async def _run_loop(
    client: AsyncOpenAI,
    agents: dict[str, Agent],
    enriched_input: str,
    history: list[dict[str, Any]],
    pref_summary: str,
    session_notes: str,
    location: dict[str, float] | None,
    location_info: dict[str, Any] | None,
    nearby_landmarks: list[dict[str, Any]],
    user_id: str,
) -> AsyncIterator[Event]:
    transcript: list[dict[str, Any]] = []
    final_answer = ""
    for step in range(MAX_STEPS):
        decision = await _ask_manager(
            client,
            _manager_messages(agents, enriched_input, history, transcript, session_notes),
        )
        next_agent = (decision.get("next_agent") or "").strip()
        subtask = decision.get("subtask") or enriched_input
        thought = decision.get("thought") or ""

        yield Event(
            "manager",
            {"step": step + 1, "thought": thought, "next_agent": next_agent},
        )

        if next_agent == "final" or not next_agent:
            final_answer = decision.get("final_answer") or "（主持人未给出最终回复）"
            break

        agent = agents.get(next_agent)
        if agent is None:
            transcript.append(
                {"agent": next_agent, "summary": "未知 agent，跳过"}
            )
            continue

        yield Event("agent_start", {"agent": next_agent, "subtask": subtask})

        extra = f"用户ID: {user_id}\n{pref_summary}"
        if session_notes:
            extra += f"\n{session_notes}"
        if location:
            extra += f"\n用户当前定位坐标: lng={location.get('lng')}, lat={location.get('lat')}"
        if location_info:
            extra += (
                "\n用户精确地址："
                f"{location_info.get('city','')}{location_info.get('district','')}"
                f"{location_info.get('township','')}"
                f"{location_info.get('neighborhood','')}"
                f"{location_info.get('street','')}{location_info.get('street_number','')}"
            ).strip()
        if nearby_landmarks:
            top = [p for p in nearby_landmarks[:5] if isinstance(p, dict) and p.get("name")]
            if top:
                extra += "\n附近最近地铁站（按距离）：" + "；".join(p["name"] for p in top)

        result = await agent.run(subtask, extra_context=extra)
        text = _sanitize_agent_text(result["text"])
        tool_results = result["tool_results"]
        transcript.append(
            {
                "agent": next_agent,
                "text": text,
                "summary": (text[:160] + "…") if len(text) > 160 else text,
            }
        )

        yield Event(
            "agent_end",
            {"agent": next_agent, "text": text, "tool_results": tool_results},
        )

        # 硬规则：planning / navigation / search 任一跑完一次并产出实质内容（>80 字
        # 且不是"达到工具调用上限"），直接 final，避免 manager 反复决策
        if (
            next_agent in {"planning_agent", "navigation_agent", "search_agent"}
            and text and len(text.strip()) > 80
            and "达到工具调用上限" not in text
        ):
            final_answer = text
            break

        # 硬规则：interaction_agent 跑完一次产出非空文字就直接 final。
        # 它的回答都比较短（自我介绍/澄清/闲聊），不必让 manager 再循环。
        if next_agent == "interaction_agent" and text and text.strip():
            final_answer = text
            break

        if next_agent == "testing_agent" and text.strip().startswith("PASS"):
            for prev in reversed(transcript[:-1]):
                if prev["agent"] != "testing_agent":
                    final_answer = prev["text"]
                    break
            else:
                final_answer = text
            break
    else:
        for prev in reversed(transcript):
            if prev["agent"] != "testing_agent" and prev.get("text", "").strip():
                final_answer = prev["text"]
                break
        if not final_answer:
            final_answer = "（达到最大步数，仍未收敛，请重新描述需求）"

    yield Event("_final", {"text": final_answer})
