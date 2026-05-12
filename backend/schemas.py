"""API 请求体模型（供路由与依赖注入共用，避免循环导入）。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatLocation(BaseModel):
    lng: float
    lat: float


class ChatRequest(BaseModel):
    """单用户 / 开发模式下无需传 ``user_id``，后端会回退到 ``DEFAULT_USER_ID``（默认 ``demo_user``）；
    多用户模式下以 JWT ``sub`` 为准。``user_id`` 字段仅保留向后兼容，可省略。

    ``conversation_id`` 不传时使用该用户最新（未归档）会话；都没有就自动新建一个。

    replace_message_id 不为空时表示"编辑这条历史用户消息并重新生成"：
    后端会先把该 id 处的消息内容替换为 ``message``，并删除其后所有消息，再触发 orchestration。
    """
    user_id: str | None = Field(default=None, max_length=256)
    conversation_id: str | None = Field(default=None, max_length=36)
    message: str = Field(..., min_length=1, max_length=32000)
    location: ChatLocation | None = None
    replace_message_id: int | None = Field(default=None, ge=1)


class EditMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=32000)


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class UpdateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    archived: bool | None = None
