"""测试 agent：对最终回复做一次质检（事实/字段缺失/链接齐全）。"""
from __future__ import annotations

from backend.agents.base import Agent


def build_testing_agent() -> Agent:
    return Agent(
        name="testing_agent",
        description="对其他 agent 的输出做质检，给出 PASS / 需修改建议。",
        system_prompt=(
            "你是『测试 Agent』。检查输入回复是否：\n"
            "1. 中文表达通顺、无明显事实错误；\n"
            "2. 涉及行程时是否有时间、地点、预算；\n"
            "3. 涉及推荐时是否给出链接 / 图片；\n"
            "4. 标题与内容必须一致：例如『🏨 推荐酒店』标题下必须是酒店条目，"
            "如果是行程表格或者上一节的延续内容，必须 WARN；\n"
            "5. 不要重写整个回复，只输出一行评价：以『PASS:』或『WARN:』开头，后接 1 句话。"
        ),
    )
