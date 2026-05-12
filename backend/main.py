"""FastAPI 入口：
- POST /api/auth/register|login|me   账户与 JWT（AUTH_REQUIRED=true 时启用）
- POST /api/chat            SSE 流；用户身份来自 JWT 或（仅开发）JSON user_id
- GET  /api/memory          查看偏好与历史（鉴权：Bearer；开发：?user_id=）
- DEL  /api/memory          清空记忆
- GET  /api/reverse         经纬度反查地址
- GET  /api/healthz         健康检查（含各 MCP 状态）
- GET  /                    托管前端 index.html
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from backend.auth.deps import chat_effective_user_id, memory_effective_user_id
from backend.auth.router import router as auth_router
from backend.config import settings
from backend.memory.memory_store import memory_store
from backend.memory.short_term import short_term_memory
from backend.mcp import amap
from backend.observability import instrument_fastapi, setup_otel
from backend.orchestrator import run_orchestration
from backend.providers import get_session
from backend.schemas import (
    ChatRequest,
    CreateConversationRequest,
    EditMessageRequest,
    UpdateConversationRequest,
)

setup_otel(service_name="travelagent")

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auth_required and len(settings.jwt_secret.strip()) < 16:
        raise RuntimeError(
            "AUTH_REQUIRED=true 时必须配置 JWT_SECRET（建议至少 32 字符的随机串）"
        )
    await memory_store.init()
    yield
    await memory_store.close()


app = FastAPI(title="Multi-Agent 智能旅行助手", lifespan=lifespan)
app.include_router(auth_router)

instrument_fastapi(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)




@app.post("/api/chat")
async def chat(
    req: ChatRequest,
    user_id: str = Depends(chat_effective_user_id),
):
    loc = req.location.model_dump() if req.location else None
    conversation_id = req.conversation_id

    if req.replace_message_id is not None:
        existing = await memory_store.get_message(user_id, req.replace_message_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="待编辑的消息不存在或不属于当前用户")
        if existing.get("role") != "user":
            raise HTTPException(status_code=400, detail="只允许重新生成『用户消息』")
        await memory_store.update_message(user_id, req.replace_message_id, req.message)
        await memory_store.truncate_from(
            user_id, req.replace_message_id, inclusive=False
        )

    if conversation_id is not None:
        conv = await memory_store.get_conversation(user_id, conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在或不属于当前用户")

    async def event_gen():
        async for ev in run_orchestration(
            user_id,
            req.message,
            loc,
            skip_user_persist=req.replace_message_id is not None,
            conversation_id=conversation_id,
        ):
            yield ev.to_sse()

    return EventSourceResponse(event_gen())


@app.get("/api/memory")
async def get_memory(
    user_id: str = Depends(memory_effective_user_id),
    conversation_id: str | None = None,
):
    """返回分层记忆视图：
    - ``long_term``：跨对话持久化的用户偏好（DB）
    - ``short_term``：当前会话便签 + 缓存消息（进程内，重启后消失）
    - ``history``：本会话 DB 消息列表（向后兼容）
    """
    user_blob = await memory_store.get_user(user_id, conversation_id)
    active_cid = user_blob.get("conversation_id") or conversation_id
    st_snapshot = (
        short_term_memory.snapshot(active_cid) if active_cid else {"messages": [], "notes": []}
    )
    return {
        "long_term": {
            "preferences": user_blob.get("preferences", []),
        },
        "short_term": {
            "conversation_id": active_cid,
            "notes": st_snapshot["notes"],
            "cached_messages_count": len(st_snapshot["messages"]),
        },
        # 向后兼容原有字段
        "preferences": user_blob.get("preferences", []),
        "history": user_blob.get("history", []),
        "conversation_id": active_cid,
    }


@app.delete("/api/memory")
async def clear_memory(user_id: str = Depends(memory_effective_user_id)):
    await memory_store.clear_user(user_id)
    return {"ok": True}


@app.get("/api/messages")
async def list_messages(
    user_id: str = Depends(memory_effective_user_id),
    conversation_id: str | None = None,
):
    """返回某会话的消息（含 id），按时间升序。

    ``conversation_id`` 省略时取该用户最新（未归档）会话；用户无任何会话时返回空。
    响应里同时回传 ``conversation_id``（实际取到的那个），前端可记住作为默认会话。
    """
    msgs = await memory_store.list_messages(user_id, conversation_id)
    user_blob = await memory_store.get_user(user_id, conversation_id)
    return {"messages": msgs, "conversation_id": user_blob.get("conversation_id")}


@app.get("/api/conversations")
async def list_conversations(user_id: str = Depends(memory_effective_user_id)):
    return {"conversations": await memory_store.list_conversations(user_id)}


@app.post("/api/conversations")
async def create_conversation(
    body: CreateConversationRequest,
    user_id: str = Depends(memory_effective_user_id),
):
    conv = await memory_store.create_conversation(user_id, body.title)
    return conv


@app.patch("/api/conversations/{conversation_id}")
async def patch_conversation(
    conversation_id: str,
    body: UpdateConversationRequest,
    user_id: str = Depends(memory_effective_user_id),
):
    ok = await memory_store.update_conversation(
        user_id, conversation_id, title=body.title, archived=body.archived
    )
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或不属于当前用户")
    conv = await memory_store.get_conversation(user_id, conversation_id)
    return conv or {"id": conversation_id}


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(memory_effective_user_id),
):
    ok = await memory_store.delete_conversation(user_id, conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或不属于当前用户")
    return {"ok": True}


@app.patch("/api/messages/{message_id}")
async def patch_message(
    message_id: int,
    req: EditMessageRequest,
    user_id: str = Depends(memory_effective_user_id),
):
    ok = await memory_store.update_message(user_id, message_id, req.content)
    if not ok:
        raise HTTPException(status_code=404, detail="消息不存在或不属于当前用户")
    return {"ok": True, "id": message_id, "content": req.content}


@app.delete("/api/messages/{message_id}")
async def remove_message(
    message_id: int,
    after: bool = False,
    user_id: str = Depends(memory_effective_user_id),
):
    """删除单条消息（默认）；``after=true`` 时连带删除该条及之后所有消息。"""
    if after:
        n = await memory_store.truncate_from(user_id, message_id, inclusive=True)
        if n == 0:
            raise HTTPException(status_code=404, detail="消息不存在或不属于当前用户")
        return {"ok": True, "deleted": n, "mode": "after"}
    ok = await memory_store.delete_message(user_id, message_id)
    if not ok:
        raise HTTPException(status_code=404, detail="消息不存在或不属于当前用户")
    return {"ok": True, "deleted": 1, "mode": "single"}


@app.get("/api/reverse")
async def reverse(lng: float, lat: float):
    try:
        return await amap.reverse_geocode(lng, lat)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.get("/api/config")
async def public_config():
    """前端需要的公开配置（不含敏感秘钥的 server 端 token）。"""
    return {
        "amap_js_key": settings.amap_js_key,
        "amap_js_security": settings.amap_js_security,
        "auth_required": settings.auth_required,
    }


@app.get("/api/healthz")
async def healthz():
    try:
        sess = get_session()
        provider, model, manager_model = sess.provider, sess.model, sess.manager_model
    except Exception as e:
        provider, model, manager_model = f"error: {e}", "", ""
    return {
        "ok": True,
        "demo_mode": settings.demo_mode,
        "provider": provider,
        "model": model,
        "manager_model": manager_model,
        "memory": "sqlite" if "sqlite" in settings.database_url.lower() else "other",
        "auth_required": settings.auth_required,
        "mcp": {
            "amap": bool(settings.amap_mcp_url),
            "xhs": bool(settings.xhs_mcp_url),
            "train12306": bool(settings.train12306_mcp_url),
            "hotel": bool(settings.hotel_mcp_url),
            "variflight": bool(settings.variflight_mcp_url),
        },
    }


# 静态前端
if FRONTEND.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(FRONTEND)),
        name="static",
    )

    @app.get("/")
    async def index():
        return FileResponse(str(FRONTEND / "index.html"))


def main() -> None:
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
