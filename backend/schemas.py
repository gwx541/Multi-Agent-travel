"""API 请求体模型（供路由与依赖注入共用，避免循环导入）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatLocation(BaseModel):
    lng: float
    lat: float


class ChatHistoryItem(BaseModel):
    """客户端上传的一条历史消息（用作本轮上下文）。"""
    role: str = Field(..., max_length=16)
    content: str = Field(..., max_length=32000)


class ChatRequest(BaseModel):
    """无状态记忆模式：记忆全部保存在客户端（手机本地）。

    每次会话时由客户端把『长期偏好』与『近期会话上下文』随请求带上，后端据此拼 prompt，
    **不再持久化任何记忆**；识别到的新偏好通过 SSE ``final`` 事件的 ``new_preferences`` 回传，
    由客户端写入本地长期记忆文件。

    - ``preferences``：客户端保存的长期偏好列表（跨对话）。
    - ``history``：近期会话消息（按时间升序），仅用于本轮上下文，不落库。
    - ``need_title``：为 True 时后端基于本轮输入回传一个会话短标题（客户端自行保存）。
    - ``user_id`` / ``conversation_id`` 仅作向后兼容，可省略。
    """
    user_id: str | None = Field(default=None, max_length=256)
    conversation_id: str | None = Field(default=None, max_length=36)
    message: str = Field(..., min_length=1, max_length=32000)
    location: ChatLocation | None = None
    replace_message_id: int | None = Field(default=None, ge=1)
    preferences: list[str] | None = Field(default=None, max_length=200)
    history: list[ChatHistoryItem] | None = Field(default=None, max_length=200)
    need_title: bool = False


class EditMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=32000)


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class UpdateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    archived: bool | None = None
