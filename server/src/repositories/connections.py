from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.postgres.connections import ConnectionModel, _link_code


class ConnectionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: UUID) -> ConnectionModel | None:
        result = await self.session.execute(select(ConnectionModel).where(ConnectionModel.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_telegram_chat_id(self, chat_id: str) -> ConnectionModel | None:
        result = await self.session.execute(select(ConnectionModel).where(ConnectionModel.telegram_chat_id == chat_id))
        return result.scalar_one_or_none()

    async def get_by_link_code(self, code: str) -> ConnectionModel | None:
        result = await self.session.execute(select(ConnectionModel).where(ConnectionModel.telegram_link_code == code))
        return result.scalar_one_or_none()

    async def get_or_create(self, user_id: UUID) -> ConnectionModel:
        conn = await self.get_by_user_id(user_id)
        if conn is not None:
            return conn
        conn = ConnectionModel(user_id=user_id)
        self.session.add(conn)
        await self.session.commit()
        await self.session.refresh(conn)
        return conn

    async def link_telegram(self, code: str, chat_id: str) -> ConnectionModel | None:
        """Bind a Telegram chat to the connection owning ``code``. Returns None on refusal.

        Single-use code + refusing to re-point an already-linked connection both guard against chat hijack
        if a link URL leaks.
        """
        conn = await self.get_by_link_code(code)
        if conn is None:
            return None
        if conn.telegram_chat_id and conn.telegram_chat_id != chat_id:
            return None
        conn.telegram_chat_id = chat_id
        conn.telegram_link_code = _link_code()  # rotate: the code cannot be reused
        try:
            await self.session.commit()
        except IntegrityError:
            # chat_id already linked to another user (unique constraint)
            await self.session.rollback()
            return None
        await self.session.refresh(conn)
        return conn

    async def link_chat_to_user(self, user_id: UUID, chat_id: str) -> bool:
        """Bind a Telegram chat to ``user_id`` directly (the Telegram-initiated GitHub login).

        One chat per user: this (re-)points the user's connection to ``chat_id`` — logging in
        from a new chat moves delivery there (latest wins). Anti-hijack: refuse if the chat is
        already linked to a *different* user. Returns True on link, False on refusal.
        """
        existing = await self.get_by_telegram_chat_id(chat_id)
        if existing is not None and existing.user_id != user_id:
            return False
        conn = await self.get_or_create(user_id)
        conn.telegram_chat_id = chat_id
        conn.telegram_link_code = _link_code()  # rotate any outstanding /start code
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return False
        await self.session.refresh(conn)
        return True

    async def mark_fed(self, conn: ConnectionModel) -> None:
        conn.last_feed_at = datetime.now(UTC)
        await self.session.commit()

    async def set_schedule(
        self, user_id: UUID, *, interval_minutes: int | None = None, enabled: bool | None = None
    ) -> ConnectionModel:
        """Update the user's feed cadence and/or pause-state (the user-facing schedule control)."""
        conn = await self.get_or_create(user_id)
        if interval_minutes is not None:
            conn.feed_interval_minutes = max(interval_minutes, 60)  # clamp out sub-hour spam
        if enabled is not None:
            conn.feed_enabled = enabled
        await self.session.commit()
        await self.session.refresh(conn)
        return conn

    async def list_feedable(self) -> list[ConnectionModel]:
        """Connections eligible for the scheduled feed."""
        result = await self.session.execute(
            select(ConnectionModel).where(
                ConnectionModel.feed_enabled.is_(True),
                ConnectionModel.telegram_chat_id.is_not(None),
            )
        )
        return list(result.scalars().all())
