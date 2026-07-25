from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import User, Session as DbSession, Signal, Synthesis, Akme, Message, utcnow


logger = logging.getLogger(__name__)


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

    async def get_consent_version(self, telegram_id: int) -> str | None:
        """
        Действующая редакция согласия этого пользователя. None — согласия нет.

        Читается до любого сбора данных: без согласия не создаётся ни сессия,
        ни сообщения, ни вызов LLM.
        """
        res = await self.db.execute(
            select(User.consent_version)
            .where(User.telegram_id == telegram_id, User.consent_at.isnot(None))
        )
        row = res.first()
        return row[0] if row else None

    async def set_consent(self, telegram_id: int, username: str | None, version: str) -> None:
        stmt = insert(User).values(
            telegram_id=telegram_id,
            username=username,
            consent_at=utcnow(),
            consent_version=version,
        ).on_conflict_do_update(
            index_elements=[User.telegram_id],
            set_={"username": username, "consent_at": utcnow(), "consent_version": version},
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def delete_user(self, telegram_id: int) -> bool:
        """
        Право на удаление: сносим пользователя, каскад забирает сессии, сообщения,
        сигналы, синтезы и akme. Возвращает False, если удалять было нечего.
        """
        res = await self.db.execute(delete(User).where(User.telegram_id == telegram_id))
        await self.db.commit()
        return bool(res.rowcount)

    async def delete_expired_sessions(self, days: int) -> int:
        """
        Ретеншен: сессии старше `days` дней удаляются каскадом.

        Пользователь и его согласие остаются — удаляются только разговоры.
        """
        cutoff = utcnow() - timedelta(days=days)
        res = await self.db.execute(delete(DbSession).where(DbSession.started_at < cutoff))
        await self.db.commit()
        return res.rowcount or 0

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
        except IntegrityError:
            # дубль по uq_signal_nodup_trait — ожидаемо, откатываем и продолжаем
            await self.db.rollback()
        except Exception:
            # Всё остальное — не «ну бывает». Раньше здесь глушилось любое
            # исключение, и из-за этого несовпадение типов колонок молча съедало
            # ВСЕ наблюдения: в памяти они были, в БД не появлялось ни одного.
            await self.db.rollback()
            logger.exception("Не удалось сохранить наблюдения сессии %s", session_id)
            raise

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
