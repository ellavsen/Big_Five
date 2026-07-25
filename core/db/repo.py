from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import User, Session as DbSession, Signal, Synthesis, Akme, Message, utcnow


class Repo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert_user(self, telegram_id: int, username: str | None) -> None:
        stmt = insert(User).values(
            telegram_id=telegram_id,
            username=username,
        ).on_conflict_do_update(
            index_elements=[User.telegram_id],
            set_={"username": username},
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def add_message(
        self,
        session_id: uuid.UUID,
        role: str,
        text: str,
        source: str = "text",
    ) -> int:
        msg = Message(
            session_id=session_id,
            role=role,
            text=text,
            source=source,
        )
        self.db.add(msg)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg.id
    
    async def create_session(self, telegram_id: int) -> uuid.UUID:
        s = DbSession(user_id=telegram_id)
        self.db.add(s)
        await self.db.commit()
        await self.db.refresh(s)
        return s.id

    async def touch_session_state(
        self,
        session_id: uuid.UUID,
        validity_level: int,
        dialogue_saturated: bool,
        state_json: dict | None = None,
    ) -> None:
        stmt = (
            update(DbSession)
            .where(DbSession.id == session_id)
            .values(
                validity_level_end=validity_level,
                dialogue_saturated=dialogue_saturated,
                state_json=state_json,
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def finish_session(self, session_id: uuid.UUID, validity_level_end: int, dialogue_saturated: bool, status: str = "finished") -> None:
        stmt = (
            update(DbSession)
            .where(DbSession.id == session_id)
            .values(
                finished_at=utcnow(),
                validity_level_end=validity_level_end,
                dialogue_saturated=dialogue_saturated,
                status=status,
                # сессия закрыта — рабочий снимок профиля больше не нужен
                state_json=None,
            )
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def get_active_session(self, telegram_id: int) -> tuple[uuid.UUID, dict | None] | None:
        """
        Последняя незакрытая сессия пользователя и её снимок состояния.
        Снимок может быть None: сессия создана, но процесс упал до первого хода.
        """
        res = await self.db.execute(
            select(DbSession.id, DbSession.state_json)
            .where(DbSession.user_id == telegram_id, DbSession.status == "active")
            .order_by(DbSession.started_at.desc())
            .limit(1)
        )
        row = res.first()
        return (row[0], row[1]) if row else None

    async def get_last_profile(self, telegram_id: int) -> tuple[datetime, dict] | None:
        """
        Последний завершённый профиль пользователя: когда и что вышло.

        Нужен, чтобы новый разговор начинался не с чистого листа. Берём `raw_json`
        (это `SynthesisResult.model_dump()`), а не текст итога — из него нужны
        только черты и заметки.
        """
        res = await self.db.execute(
            select(Synthesis.created_at, Synthesis.raw_json)
            .join(DbSession, DbSession.id == Synthesis.session_id)
            .where(DbSession.user_id == telegram_id, Synthesis.raw_json.isnot(None))
            .order_by(Synthesis.created_at.desc())
            .limit(1)
        )
        row = res.first()
        return (row[0], row[1]) if row else None

    async def add_signals(self, session_id: uuid.UUID, signals: list[dict]) -> None:
        """
        signals: list of dicts with keys:
        trait, direction, confidence, text, direct_example
        """
        if not signals:
            return

        for s in signals:
            obj = Signal(
                session_id=session_id,
                trait=str(s["trait"]),
                direction=str(s["direction"]),
                confidence=float(s.get("confidence", 0.0)),
                text=str(s.get("text", "")),
                direct_example=bool(s.get("direct_example", False)),
            )
            self.db.add(obj)

        try:
            await self.db.commit()
        except Exception:
            # на дублях по uq_signal_nodup просто откатываем и продолжаем
            await self.db.rollback()

    async def save_synthesis(self, session_id: uuid.UUID, text: str, traits_confidence: dict | None, raw_json: dict | None) -> None:
        stmt = insert(Synthesis).values(
            session_id=session_id,
            text=text,
            traits_confidence=traits_confidence,
            raw_json=raw_json,
        ).on_conflict_do_update(
            index_elements=[Synthesis.session_id],
            set_={
                "text": text,
                "traits_confidence": traits_confidence,
                "raw_json": raw_json,
            },
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def save_akme(self, session_id: uuid.UUID, recommendations_text: str, vector_json: dict | None) -> None:
        stmt = insert(Akme).values(
            session_id=session_id,
            recommendations_text=recommendations_text,
            vector_json=vector_json,
        ).on_conflict_do_update(
            index_elements=[Akme.session_id],
            set_={
                "recommendations_text": recommendations_text,
                "vector_json": vector_json,
            },
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def get_session(self, session_id: uuid.UUID) -> DbSession | None:
        res = await self.db.execute(select(DbSession).where(DbSession.id == session_id))
        return res.scalar_one_or_none()
