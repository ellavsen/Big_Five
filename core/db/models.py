from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Float,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.db.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# -----------------------
# USERS
# -----------------------

class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Согласие на обработку данных (психологический профиль = спец. категория ПДн).
    # NULL = согласие не давалось.
    # TODO (Этап 1): экран согласия перед первым диалогом + запрет сбора без consent_at;
    # TODO (Этап 1): retention — срок хранения сессий и /delete_me (право на удаление).
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_version: Mapped[str | None] = mapped_column(String(16), nullable=True)

    sessions: Mapped[list["Session"]] = relationship(back_populates="user", cascade="all, delete-orphan")


# -----------------------
# SESSIONS
# -----------------------

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    validity_level_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dialogue_saturated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)  # active/finished/reset

    # Снимок ConversationState: нужен, чтобы рестарт процесса не терял активный диалог.
    # Живёт только пока сессия активна — finish_session затирает его в NULL, потому что
    # это сырой психологический профиль (спец. категория ПДн), а итог к тому моменту
    # уже разложен по synthesis / signals / messages.
    # Колонка добавлена migrations/001_add_sessions_state_json.sql.
    #
    # none_as_null=True обязателен: по умолчанию SQLAlchemy пишет в JSON/JSONB
    # питоновский None как JSON-литерал 'null', а не как SQL NULL. Профиль при этом
    # стирается, но строка перестаёт находиться по `state_json IS NULL`.
    state_json: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")
    signals: Mapped[list["Signal"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    synthesis: Mapped["Synthesis | None"] = relationship(back_populates="session", uselist=False, cascade="all, delete-orphan")
    akme: Mapped["Akme | None"] = relationship(back_populates="session", uselist=False, cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="session", cascade="all, delete-orphan")



# -----------------------
# SIGNALS
# -----------------------

class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)

    axis: Mapped[str] = mapped_column(String(8), nullable=False)        # EI/SN/TF/JP
    direction: Mapped[str] = mapped_column(String(4), nullable=False)   # E/I, S/N, T/F, J/P
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


    text: Mapped[str] = mapped_column(Text, nullable=False)
    direct_example: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    session: Mapped["Session"] = relationship(back_populates="signals")

    __table_args__ = (
        # защита от дублей “один и тот же сигнал”
        UniqueConstraint("session_id", "axis", "direction", "text", name="uq_signal_nodup"),
    )


# -----------------------
# SYNTHESIS
# -----------------------

class Synthesis(Base):
    __tablename__ = "synthesis"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    axes_confidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    session: Mapped["Session"] = relationship(back_populates="synthesis")


# -----------------------
# AKME
# -----------------------

class Akme(Base):
    __tablename__ = "akme"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True)

    recommendations_text: Mapped[str] = mapped_column(Text, nullable=False)
    vector_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    session: Mapped["Session"] = relationship(back_populates="akme")

# -----------------------
# MESSAGES (transcript/history)
# -----------------------

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False
    )

    role: Mapped[str] = mapped_column(String(16), nullable=False)  
    # "user" / "assistant"

    source: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    # "text" / "voice_transcript" / "transcript_fix" / "system"

    text: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        nullable=False
    )

    session: Mapped["Session"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_messages_session_created", "session_id", "created_at"),
    )