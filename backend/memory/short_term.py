"""短期记忆：进程内、按会话缓存，服务重启后消失。

- 键：conversation_id
- 存：本会话的完整消息列表 + 会话级便签（不写库）
- 自动过期：超过 SESSION_EXPIRE_SECS 没有活动后下次访问时清理
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

SESSION_EXPIRE_SECS = 30 * 60  # 30 分钟无活动自动过期


@dataclass
class _SessionData:
    conversation_id: str
    messages: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # 会话级便签，不跨对话
    last_active: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_active = time.monotonic()

    def is_expired(self) -> bool:
        return (time.monotonic() - self.last_active) > SESSION_EXPIRE_SECS


class ShortTermMemory:
    """进程内短期记忆，按 conversation_id 存储。

    - ``messages``：当前 runtime 会话里追加的消息（与 DB 对应，但无需查库）
    - ``notes``：由 interaction_agent 提取并保存的会话级事实便签
      （如出行人数、当前规划目的地、出发日期等），仅在本次会话有效。
    """

    def __init__(self) -> None:
        self._store: dict[str, _SessionData] = {}

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #

    def _get_or_create(self, conversation_id: str) -> _SessionData:
        self._evict_expired()
        if conversation_id not in self._store:
            self._store[conversation_id] = _SessionData(conversation_id=conversation_id)
        session = self._store[conversation_id]
        session.touch()
        return session

    def _evict_expired(self) -> None:
        expired = [k for k, v in self._store.items() if v.is_expired()]
        for k in expired:
            del self._store[k]

    # ------------------------------------------------------------------ #
    # 消息操作
    # ------------------------------------------------------------------ #

    def append_message(self, conversation_id: str, role: str, content: str) -> None:
        """追加一条消息到短期缓存（不写 DB）。"""
        session = self._get_or_create(conversation_id)
        session.messages.append({"role": role, "content": content})

    def get_messages(self, conversation_id: str) -> list[dict[str, str]]:
        """获取本会话短期消息列表（按添加顺序）。会话过期或不存在返回空列表。"""
        session = self._store.get(conversation_id)
        if session is None:
            return []
        if session.is_expired():
            del self._store[conversation_id]
            return []
        return list(session.messages)

    # ------------------------------------------------------------------ #
    # 便签操作（session notes）
    # ------------------------------------------------------------------ #

    def add_note(self, conversation_id: str, note: str) -> None:
        """保存一条会话级便签（去重，只在本次会话有效）。"""
        note = (note or "").strip()
        if not note:
            return
        session = self._get_or_create(conversation_id)
        if note not in session.notes:
            session.notes.append(note)

    def get_notes(self, conversation_id: str) -> list[str]:
        """获取本会话所有便签。"""
        session = self._store.get(conversation_id)
        if session is None:
            return []
        if session.is_expired():
            del self._store[conversation_id]
            return []
        return list(session.notes)

    def notes_summary(self, conversation_id: str) -> str:
        """生成便签的 prompt 摘要，无便签时返回空字符串。"""
        notes = self.get_notes(conversation_id)
        if not notes:
            return ""
        return "【本次会话记录】" + "；".join(notes)

    # ------------------------------------------------------------------ #
    # 其他
    # ------------------------------------------------------------------ #

    def snapshot(self, conversation_id: str) -> dict[str, Any]:
        """返回该会话短期记忆的快照（供 /api/memory 等接口展示）。"""
        session = self._store.get(conversation_id)
        if session is None or session.is_expired():
            return {"messages": [], "notes": []}
        return {
            "messages": list(session.messages),
            "notes": list(session.notes),
        }

    def clear(self, conversation_id: str) -> None:
        self._store.pop(conversation_id, None)


# 全局单例
short_term_memory = ShortTermMemory()
