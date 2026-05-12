"""用户偏好与对话历史持久化（SQLAlchemy 异步）。

- 未设置 ``DATABASE_URL`` 时默认 ``SQLite``：``data/memory.db``（与旧 JSON 同目录）。
- 生产可设 ``postgresql+asyncpg://user:pass@host:5432/dbname``。
- 若存在 ``data/memory.json`` 且库里尚无聊天记录，启动时会自动导入一次并重命名为
  ``memory.json.bak``（幂等）。
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from sqlalchemy import delete, event, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import settings
from backend.db.models import (
    Account,
    Base,
    ChatHistory,
    Conversation,
    User,
    UserPreference,
)
from backend.memory.short_term import ShortTermMemory, short_term_memory

logger = logging.getLogger(__name__)

_HISTORY_LIMIT = 40


def _sqlite_pragma_foreign_keys(dbapi_conn, _connection_record) -> None:
    """SQLite 默认不强制外键；开启后 User 删除会级联子表。"""
    dbapi_conn.execute("PRAGMA foreign_keys=ON")


class DatabaseMemoryStore:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def init(self) -> None:
        if self._engine is not None:
            return
        self._engine = create_async_engine(
            settings.database_url,
            echo=_env_bool("SQL_ECHO", False),
            pool_pre_ping=True,
        )
        if self._engine.sync_engine.dialect.name == "sqlite":
            event.listen(
                self._engine.sync_engine,
                "connect",
                _sqlite_pragma_foreign_keys,
            )
        self._session_factory = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            autoflush=False,
        )
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await self._migrate_legacy_json_if_needed()
        await self._migrate_add_conversation_column_if_needed()
        await self._migrate_orphan_messages_into_legacy_conversation()
        logger.info("[memory] DB ready: %s", _safe_db_log(settings.database_url))

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    def _require_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            raise RuntimeError(
                "记忆库未初始化：请在 FastAPI lifespan 中调用 await memory_store.init()，"
                "或使用 uvicorn 启动应用。"
            )
        return self._session_factory

    def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        """供注册/登录等路由与记忆库共用同一引擎。"""
        return self._require_factory()

    async def get_user(
        self, user_id: str, conversation_id: str | None = None
    ) -> dict[str, Any]:
        """返回某个会话的消息（默认取该用户最新会话）。"""
        fac = self._require_factory()
        async with fac() as session:
            await self._ensure_user(session, user_id)
            prefs = (
                await session.scalars(
                    select(UserPreference.text).where(UserPreference.user_id == user_id)
                )
            ).all()
            cid = conversation_id
            if cid is None:
                cid = await self._latest_conversation_id(session, user_id)
            history: list[dict[str, str]] = []
            if cid is not None:
                rows = (
                    await session.execute(
                        select(ChatHistory.role, ChatHistory.content)
                        .where(ChatHistory.user_id == user_id)
                        .where(ChatHistory.conversation_id == cid)
                        .order_by(
                            ChatHistory.created_at.desc(), ChatHistory.id.desc()
                        )
                        .limit(_HISTORY_LIMIT)
                    )
                ).all()
                history = [{"role": r, "content": c} for r, c in reversed(rows)]
            return {
                "preferences": list(prefs),
                "history": history,
                "conversation_id": cid,
            }

    @staticmethod
    async def _latest_conversation_id(
        session: AsyncSession, user_id: str
    ) -> str | None:
        """按"最新发言"取该用户最近活跃的（未归档）会话，无消息的兜底用 updated_at。"""
        agg_subq = (
            select(
                ChatHistory.conversation_id,
                func.max(ChatHistory.id).label("last_mid"),
            )
            .where(ChatHistory.user_id == user_id)
            .group_by(ChatHistory.conversation_id)
            .subquery()
        )
        row = await session.scalar(
            select(Conversation.id)
            .outerjoin(agg_subq, Conversation.id == agg_subq.c.conversation_id)
            .where(Conversation.user_id == user_id)
            .where(Conversation.archived == False)  # noqa: E712
            .order_by(
                agg_subq.c.last_mid.desc().nullslast(),
                Conversation.updated_at.desc(),
                Conversation.id.desc(),
            )
            .limit(1)
        )
        return row

    async def add_preference(self, user_id: str, pref: str) -> None:
        pref = pref.strip()
        if not pref:
            return
        fac = self._require_factory()
        async with fac() as session:
            await self._ensure_user(session, user_id)
            session.add(UserPreference(user_id=user_id, text=pref))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()

    async def append_history(
        self,
        user_id: str,
        role: str,
        content: str,
        conversation_id: str | None = None,
    ) -> int:
        """追加一条消息（必须指定 conversation_id），返回新消息 id。

        若 ``conversation_id`` 为 ``None``：
        - 取该用户最新（未归档）会话；
        - 仍为空时自动新建一个未命名会话。
        """
        fac = self._require_factory()
        async with fac() as session:
            await self._ensure_user(session, user_id)
            cid = conversation_id
            if cid is None:
                cid = await self._latest_conversation_id(session, user_id)
            if cid is None:
                cid = await self._create_conversation(session, user_id)
            else:
                await self._touch_conversation(session, cid)
            row = ChatHistory(
                user_id=user_id, role=role, content=content, conversation_id=cid
            )
            session.add(row)
            await session.flush()
            new_id = row.id
            # 仅在「当前 conversation」内按 _HISTORY_LIMIT 截断旧消息
            subq = (
                select(ChatHistory.id)
                .where(ChatHistory.user_id == user_id)
                .where(ChatHistory.conversation_id == cid)
                .order_by(ChatHistory.created_at.desc(), ChatHistory.id.desc())
                .offset(_HISTORY_LIMIT)
            )
            old_ids = (await session.scalars(subq)).all()
            if old_ids:
                await session.execute(
                    delete(ChatHistory).where(ChatHistory.id.in_(old_ids))
                )
            await session.commit()
            return new_id

    async def list_messages(
        self, user_id: str, conversation_id: str | None = None
    ) -> list[dict[str, Any]]:
        """按时间升序返回该会话的消息（含 id），上限 _HISTORY_LIMIT。

        ``conversation_id`` 为 ``None`` 时取最新会话；该用户无任何会话时返回 ``[]``。
        """
        fac = self._require_factory()
        async with fac() as session:
            await self._ensure_user(session, user_id)
            cid = conversation_id
            if cid is None:
                cid = await self._latest_conversation_id(session, user_id)
            if cid is None:
                return []
            rows = (
                await session.execute(
                    select(
                        ChatHistory.id,
                        ChatHistory.role,
                        ChatHistory.content,
                        ChatHistory.created_at,
                    )
                    .where(ChatHistory.user_id == user_id)
                    .where(ChatHistory.conversation_id == cid)
                    .order_by(ChatHistory.created_at.desc(), ChatHistory.id.desc())
                    .limit(_HISTORY_LIMIT)
                )
            ).all()
        rows = list(reversed(rows))
        return [
            {
                "id": mid,
                "role": role,
                "content": content,
                "created_at": created_at.isoformat() if created_at else None,
            }
            for (mid, role, content, created_at) in rows
        ]

    # -------- Conversation CRUD --------

    @staticmethod
    async def _create_conversation(
        session: AsyncSession, user_id: str, title: str | None = None
    ) -> str:
        cid = str(uuid.uuid4())
        session.add(Conversation(id=cid, user_id=user_id, title=title))
        await session.flush()
        return cid

    @staticmethod
    async def _touch_conversation(session: AsyncSession, cid: str) -> None:
        await session.execute(
            update(Conversation)
            .where(Conversation.id == cid)
            .values(updated_at=func.now())
        )

    async def create_conversation(
        self, user_id: str, title: str | None = None
    ) -> dict[str, Any]:
        fac = self._require_factory()
        async with fac() as session:
            await self._ensure_user(session, user_id)
            cid = await self._create_conversation(session, user_id, title)
            await session.commit()
            return await self._conv_to_dict_by_id(session, cid)

    async def list_conversations(self, user_id: str) -> list[dict[str, Any]]:
        """按"最新发言"倒序返回会话；空会话按 ``updated_at`` 倒序排到后面。"""
        fac = self._require_factory()
        async with fac() as session:
            await self._ensure_user(session, user_id)
            # 用 chat_history.id 的最大值作为"最近活跃度"——它是 autoincrement，
            # 单调递增，可以避免 SQLite created_at 仅到秒精度造成的排序歧义。
            agg_subq = (
                select(
                    ChatHistory.conversation_id,
                    func.count(ChatHistory.id).label("cnt"),
                    func.max(ChatHistory.id).label("last_mid"),
                )
                .where(ChatHistory.user_id == user_id)
                .group_by(ChatHistory.conversation_id)
                .subquery()
            )
            rows = (
                await session.execute(
                    select(
                        Conversation.id,
                        Conversation.title,
                        Conversation.created_at,
                        Conversation.updated_at,
                        Conversation.archived,
                        agg_subq.c.cnt,
                        agg_subq.c.last_mid,
                    )
                    .outerjoin(agg_subq, Conversation.id == agg_subq.c.conversation_id)
                    .where(Conversation.user_id == user_id)
                    .order_by(
                        agg_subq.c.last_mid.desc().nullslast(),
                        Conversation.updated_at.desc(),
                        Conversation.id.desc(),
                    )
                )
            ).all()
            return [
                {
                    "id": cid,
                    "title": title,
                    "created_at": created_at.isoformat() if created_at else None,
                    "updated_at": updated_at.isoformat() if updated_at else None,
                    "archived": bool(archived),
                    "message_count": int(cnt or 0),
                }
                for (cid, title, created_at, updated_at, archived, cnt, _last) in rows
            ]

    async def get_conversation(
        self, user_id: str, conversation_id: str
    ) -> dict[str, Any] | None:
        fac = self._require_factory()
        async with fac() as session:
            conv = await session.get(Conversation, conversation_id)
            if conv is None or conv.user_id != user_id:
                return None
            return await self._conv_to_dict_by_id(session, conversation_id)

    async def needs_auto_title(
        self, user_id: str, conversation_id: str
    ) -> bool:
        """该会话是否需要自动生成标题：title 为空 / 已被改成默认占位时返回 True。"""
        fac = self._require_factory()
        async with fac() as session:
            conv = await session.get(Conversation, conversation_id)
            if conv is None or conv.user_id != user_id:
                return False
            return not (conv.title or "").strip()

    async def update_conversation(
        self,
        user_id: str,
        conversation_id: str,
        title: str | None = None,
        archived: bool | None = None,
    ) -> bool:
        fac = self._require_factory()
        async with fac() as session:
            conv = await session.get(Conversation, conversation_id)
            if conv is None or conv.user_id != user_id:
                return False
            if title is not None:
                conv.title = title
            if archived is not None:
                conv.archived = archived
            await session.commit()
            return True

    async def delete_conversation(self, user_id: str, conversation_id: str) -> bool:
        fac = self._require_factory()
        async with fac() as session:
            conv = await session.get(Conversation, conversation_id)
            if conv is None or conv.user_id != user_id:
                return False
            await session.delete(conv)
            await session.commit()
            return True

    @staticmethod
    async def _conv_to_dict_by_id(
        session: AsyncSession, conversation_id: str
    ) -> dict[str, Any]:
        conv = await session.get(Conversation, conversation_id)
        if conv is None:
            return {}
        cnt = await session.scalar(
            select(func.count(ChatHistory.id)).where(
                ChatHistory.conversation_id == conversation_id
            )
        )
        return {
            "id": conv.id,
            "title": conv.title,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
            "archived": bool(conv.archived),
            "message_count": int(cnt or 0),
        }

    async def update_message(
        self, user_id: str, message_id: int, content: str
    ) -> bool:
        """就地修改一条消息的内容；返回是否命中。"""
        fac = self._require_factory()
        async with fac() as session:
            row = await session.get(ChatHistory, message_id)
            if row is None or row.user_id != user_id:
                return False
            row.content = content
            await session.commit()
            return True

    async def get_message(
        self, user_id: str, message_id: int
    ) -> dict[str, Any] | None:
        fac = self._require_factory()
        async with fac() as session:
            row = await session.get(ChatHistory, message_id)
            if row is None or row.user_id != user_id:
                return None
            return {
                "id": row.id,
                "role": row.role,
                "content": row.content,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }

    async def truncate_from(
        self, user_id: str, message_id: int, inclusive: bool = True
    ) -> int:
        """删除目标消息（含 / 不含）及其之后所有消息，返回删除条数。

        以 ``id`` 作为唯一排序键（autoincrement 单调递增），避免
        SQLite ``server_default=func.now()`` 只到秒精度导致同秒插入次序歧义。
        """
        fac = self._require_factory()
        async with fac() as session:
            anchor = await session.get(ChatHistory, message_id)
            if anchor is None or anchor.user_id != user_id:
                return 0
            cond = (
                ChatHistory.id >= anchor.id
                if inclusive
                else ChatHistory.id > anchor.id
            )
            stmt = (
                delete(ChatHistory)
                .where(ChatHistory.user_id == user_id)
                .where(cond)
            )
            result = await session.execute(stmt)
            await session.commit()
            return int(result.rowcount or 0)

    async def delete_message(self, user_id: str, message_id: int) -> bool:
        """仅删除单条消息（不影响后续消息），返回是否命中。"""
        fac = self._require_factory()
        async with fac() as session:
            row = await session.get(ChatHistory, message_id)
            if row is None or row.user_id != user_id:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def clear_user(self, user_id: str) -> None:
        fac = self._require_factory()
        async with fac() as session:
            await session.execute(delete(User).where(User.user_id == user_id))
            await session.commit()

    async def long_term_summary(self, user_id: str) -> str:
        """长期记忆摘要：跨对话持久化的用户偏好列表。"""
        u = await self.get_user(user_id)
        prefs = u.get("preferences") or []
        if not prefs:
            return "（暂无已记录的长期偏好）"
        return "【长期偏好】" + "；".join(prefs)

    async def summary_for_prompt(
        self,
        user_id: str,
        conversation_id: str | None = None,
    ) -> str:
        """生成供 prompt 注入的记忆摘要，同时包含长期偏好和短期会话便签。"""
        long_part = await self.long_term_summary(user_id)
        if conversation_id:
            short_part = short_term_memory.notes_summary(conversation_id)
        else:
            short_part = ""
        if short_part:
            return f"{long_part}\n{short_part}"
        return long_part

    @staticmethod
    async def _ensure_user(session: AsyncSession, user_id: str) -> None:
        row = await session.get(User, user_id)
        if row is None:
            session.add(User(user_id=user_id))
            await session.flush()

    async def _migrate_add_conversation_column_if_needed(self) -> None:
        """老库没有 ``conversation_id`` 列（SQLite ``create_all`` 不会改已存在表）。
        探测列是否存在，缺则 ``ALTER TABLE ADD COLUMN`` 加上。
        """
        if self._engine is None:
            return
        dialect = self._engine.sync_engine.dialect.name
        if dialect != "sqlite":
            # 其他库走正经迁移工具（如 alembic），这里不擅自 ALTER
            return
        async with self._engine.begin() as conn:
            rows = (
                await conn.execute(text("PRAGMA table_info(chat_history)"))
            ).all()
            cols = {r[1] for r in rows}
            if "conversation_id" not in cols:
                await conn.execute(
                    text(
                        "ALTER TABLE chat_history "
                        "ADD COLUMN conversation_id VARCHAR(36)"
                    )
                )
                logger.info(
                    "[memory] migrated chat_history: added conversation_id column"
                )

    async def _migrate_orphan_messages_into_legacy_conversation(self) -> None:
        """把 ``conversation_id IS NULL`` 的存量消息按 ``user_id`` 聚类，
        每个用户新建一个『早期对话』归档进去。幂等：若已无孤儿则跳过。"""
        fac = self._require_factory()
        async with fac() as session:
            orphan_users = (
                await session.scalars(
                    select(ChatHistory.user_id)
                    .where(ChatHistory.conversation_id.is_(None))
                    .group_by(ChatHistory.user_id)
                )
            ).all()
            if not orphan_users:
                return
            for uid in orphan_users:
                cid = await self._create_conversation(
                    session, uid, title="早期对话"
                )
                await session.execute(
                    update(ChatHistory)
                    .where(ChatHistory.user_id == uid)
                    .where(ChatHistory.conversation_id.is_(None))
                    .values(conversation_id=cid)
                )
            await session.commit()
            logger.info(
                "[memory] migrated orphan messages into legacy conversations for %d user(s)",
                len(orphan_users),
            )

    async def _migrate_legacy_json_if_needed(self) -> None:
        legacy = settings.data_dir / "memory.json"
        if not legacy.exists():
            return
        fac = self._require_factory()
        async with fac() as session:
            n = await session.scalar(select(func.count()).select_from(ChatHistory))
            if n and n > 0:
                return
        try:
            raw = json.loads(legacy.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("[memory] skip legacy import: %s", e)
            return
        if not isinstance(raw, dict) or not raw:
            return
        async with fac() as session:
            for uid, blob in raw.items():
                if not isinstance(blob, dict):
                    continue
                session.add(User(user_id=str(uid)))
                for p in blob.get("preferences") or []:
                    if isinstance(p, str) and p.strip():
                        session.add(UserPreference(user_id=str(uid), text=p.strip()))
                hist = blob.get("history") or []
                if isinstance(hist, list) and len(hist) > _HISTORY_LIMIT:
                    hist = hist[-_HISTORY_LIMIT:]
                for h in hist:
                    if not isinstance(h, dict):
                        continue
                    r, c = h.get("role"), h.get("content")
                    if isinstance(r, str) and isinstance(c, str):
                        session.add(
                            ChatHistory(user_id=str(uid), role=r, content=c)
                        )
            await session.commit()
        bak = legacy.with_suffix(".json.bak")
        try:
            legacy.rename(bak)
            logger.info("[memory] migrated %s -> %s", legacy, bak)
        except OSError as e:
            logger.warning("[memory] migrated DB but could not rename json: %s", e)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _safe_db_log(url: str) -> str:
    """日志里不打印密码。"""
    if "@" in url and "://" in url:
        head, _, tail = url.partition("://")
        cred, _, host = tail.partition("@")
        if ":" in cred:
            user, _, _ = cred.partition(":")
            return f"{head}://{user}:***@{host}"
    return url


memory_store = DatabaseMemoryStore()

__all__ = ["memory_store", "short_term_memory"]
