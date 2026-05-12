"""Agent 基类。
使用 OpenAI Chat Completions + tool calling，统一处理多轮工具调用循环。
所有 agent 共享同一个 AsyncOpenAI 客户端。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from openai import AsyncOpenAI

from backend.config import settings
from backend.observability import set_attr, span
from backend.providers import get_session


# DeepSeek 偶发会把 tool_calls 吐成自家 DSML 文本而不是结构化 tool_calls，需要兜底解析。
# 形如：
#   <｜｜DSML｜｜tool_calls>
#     <｜｜DSML｜｜invoke name="amap_around_search">
#       <｜｜DSML｜｜parameter name="lng">113.5</｜｜DSML｜｜parameter>
#     </｜｜DSML｜｜invoke>
#   </｜｜DSML｜｜tool_calls>
_DSML_INVOKE = re.compile(
    r"<｜｜DSML｜｜invoke\s+name=\"([^\"]+)\">(.*?)</｜｜DSML｜｜invoke>",
    re.DOTALL,
)
_DSML_PARAM = re.compile(
    r"<｜｜DSML｜｜parameter\s+name=\"([^\"]+)\"[^>]*>(.*?)</｜｜DSML｜｜parameter>",
    re.DOTALL,
)


def _parse_dsml_calls(content: str) -> list[dict[str, Any]]:
    if not content or "DSML" not in content:
        return []
    out: list[dict[str, Any]] = []
    for m in _DSML_INVOKE.finditer(content):
        name = m.group(1).strip()
        body = m.group(2)
        args: dict[str, Any] = {}
        for pm in _DSML_PARAM.finditer(body):
            key = pm.group(1).strip()
            val = pm.group(2).strip()
            if val.startswith(("{", "[")):
                try:
                    args[key] = json.loads(val)
                    continue
                except Exception:
                    pass
            try:
                if "." in val:
                    args[key] = float(val)
                else:
                    args[key] = int(val)
            except Exception:
                if val.lower() in ("true", "false"):
                    args[key] = val.lower() == "true"
                else:
                    args[key] = val
        out.append({"name": name, "arguments": json.dumps(args, ensure_ascii=False)})
    return out

def get_openai() -> AsyncOpenAI:
    """向后兼容：返回当前 provider 的客户端。
    新代码请改用 backend.providers.get_session()。"""
    return get_session().client


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class Agent:
    name: str
    description: str
    system_prompt: str
    tools: list[Tool] = field(default_factory=list)
    model: str | None = None

    async def run(self, user_input: str, extra_context: str = "") -> dict[str, Any]:
        """执行一轮 agent。返回 {text, tool_results}。tool_results 用于前端渲染卡片。"""
        sess = get_session()
        client = sess.client
        model = self.model or sess.model

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
        ]
        if extra_context:
            messages.append({"role": "system", "content": extra_context})
        messages.append({"role": "user", "content": user_input})

        tool_payload = [t.to_openai() for t in self.tools] if self.tools else None
        tool_results: list[dict[str, Any]] = []

        max_iters = 8
        with span(
            f"agent.{self.name}",
            **{
                "agent.name": self.name,
                "agent.tools_count": len(self.tools),
                "llm.model": model,
                "llm.provider": sess.provider,
                "user_input.length": len(user_input or ""),
            },
        ) as agent_sp:
            for i in range(max_iters):
                kwargs: dict[str, Any] = {"model": model, "messages": messages}
                if tool_payload:
                    kwargs["tools"] = tool_payload
                    kwargs["tool_choice"] = "none" if i == max_iters - 1 else "auto"
                with span(
                    "llm.chat",
                    **{"llm.model": model, "llm.iter": i, "llm.tools_offered": bool(tool_payload)},
                ):
                    resp = await client.chat.completions.create(**kwargs)
                msg = resp.choices[0].message
                content = msg.content or ""
                real_calls = list(msg.tool_calls or [])

                # DeepSeek 偶发把 tool_calls 写到 content 的 DSML 文本里，转成结构化调用兜底
                dsml_calls: list[dict[str, Any]] = []
                if not real_calls:
                    dsml_calls = _parse_dsml_calls(content)

                if real_calls:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [tc.model_dump() for tc in real_calls],
                        }
                    )
                    exec_list = [
                        (tc.id, tc.function.name, tc.function.arguments) for tc in real_calls
                    ]
                elif dsml_calls:
                    fake = [
                        {
                            "id": f"dsml_{idx}",
                            "type": "function",
                            "function": {"name": c["name"], "arguments": c["arguments"]},
                        }
                        for idx, c in enumerate(dsml_calls)
                    ]
                    messages.append(
                        {"role": "assistant", "content": "", "tool_calls": fake}
                    )
                    exec_list = [
                        (f"dsml_{j}", c["name"], c["arguments"])
                        for j, c in enumerate(dsml_calls)
                    ]
                else:
                    messages.append({"role": "assistant", "content": content})
                    set_attr(agent_sp, "agent.iters_used", i + 1)
                    set_attr(agent_sp, "agent.tool_calls_total", len(tool_results))
                    set_attr(agent_sp, "agent.output_length", len(content))
                    return {"text": content, "tool_results": tool_results}

                for call_id, fn_name, fn_args in exec_list:
                    tool = next((t for t in self.tools if t.name == fn_name), None)
                    with span(f"tool.{fn_name}", **{"tool.name": fn_name}) as tool_sp:
                        if tool is None:
                            payload: Any = {"error": f"未知工具 {fn_name}"}
                            set_attr(tool_sp, "tool.unknown", True)
                        else:
                            try:
                                args = json.loads(fn_args or "{}")
                                payload = await tool.handler(**args)
                            except Exception as e:
                                payload = {"error": f"{type(e).__name__}: {e}"}
                                set_attr(tool_sp, "tool.error", f"{type(e).__name__}: {e}")
                        if isinstance(payload, list):
                            set_attr(tool_sp, "tool.result_count", len(payload))
                        elif isinstance(payload, dict) and "error" in payload:
                            set_attr(tool_sp, "tool.error", str(payload["error"])[:200])
                    tool_results.append({"tool": fn_name, "data": payload})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": json.dumps(payload, ensure_ascii=False, default=str),
                        }
                    )
            # for 结束 = 达到 max_iters，仍未自然终止，进兜底
            set_attr(agent_sp, "agent.iters_used", max_iters)
            set_attr(agent_sp, "agent.tool_calls_total", len(tool_results))
            set_attr(agent_sp, "agent.exit_reason", "max_iters")

        # 兜底：再要一次纯文字总结
        try:
            with span("llm.chat", **{"llm.model": model, "llm.iter": "summary"}):
                resp = await client.chat.completions.create(
                    model=model,
                    messages=messages
                    + [
                        {
                            "role": "user",
                            "content": "请基于以上工具结果直接给出中文 markdown 答复，不再调用工具。",
                        }
                    ],
                )
            return {
                "text": resp.choices[0].message.content or "",
                "tool_results": tool_results,
            }
        except Exception:
            return {
                "text": "（达到工具调用上限，已停止迭代）",
                "tool_results": tool_results,
            }
