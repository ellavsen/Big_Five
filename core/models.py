# core/models.py
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator

class Axis(str, Enum):
    EI = "EI"
    SN = "SN"
    TF = "TF"
    JP = "JP"


class AxisDirection(str, Enum):
    # EI
    E = "E"
    I = "I"  # noqa: E741 — это полюс оси MBTI, а не переменная
    # SN
    S = "S"
    N = "N"
    # TF
    T = "T"
    F = "F"
    # JP
    J = "J"
    P = "P"


AxisSource = Literal["llm", "user", "energy", "module", "direct_example"]


class AxisSignal(BaseModel):
    """
    Один наблюдаемый сигнал по одной оси.
    direction — конкретная сторона оси (например, I или E).
    confidence — насколько уверенно этот сигнал поддерживает direction (0..1).
    """
    model_config = ConfigDict(extra="forbid")

    axis: Axis
    direction: str  # keep as str to avoid жесткой привязки к AxisDirection в раннем MVP
    text: str = Field(..., description="Короткое основание: что именно в ответе дало сигнал")
    source: AxisSource = "llm"
    # ge/le нельзя: strict-схема structured outputs не поддерживает minimum/maximum.
    # Диапазон держим валидатором — модель, вышедшую за 0..1, подрезаем, а не роняем ход.
    confidence: float = 0.6
    direct_example: bool = False

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class AxisEvidence(BaseModel):
    """
    Склад всех сигналов по всем осям.
    """
    model_config = ConfigDict(extra="forbid")

    signals: List[AxisSignal] = Field(default_factory=list)

    def add(self, sig: AxisSignal) -> None:
        self.signals.append(sig)

    def signals_for(self, axis: Axis) -> List[AxisSignal]:
        return [s for s in self.signals if s.axis == axis]

    # Алиас ради читаемости/совместимости со старым кодом
    def for_axis(self, axis: Axis) -> List[AxisSignal]:
        return self.signals_for(axis)


class Goals(BaseModel):
    """
    Прогресс диагностических целей (1..10).
    """
    model_config = ConfigDict(extra="forbid")

    ctx: int = 3
    sig: int = 3
    val: int = 3
    map: int = 1
    sum: int = 1


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant", "system"]
    content: str


class TurnPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    A: Literal["ask", "interpret"]
    message: str
    axis_signals: List[AxisSignal] = []


# =========================
# Форма ответа синтезатора.
#
# Все контейнеры здесь — с фиксированными ключами. Это требование strict-схемы
# structured outputs: открытые словари ({"EI": ...} как additionalProperties)
# API не принимает. Поэтому оси перечислены полями, а probabilities — списком пар.
# Значения по умолчанию нужны только fallback-пути в core/llm.py: в самой схеме
# все поля обязательны, модель обязана вернуть их целиком.
# =========================

class AxisConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence: float = 0.0  # 0.0–1.0
    stability: Literal["устойчивая", "пограничная"] = "пограничная"


class AxesConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    EI: AxisConfidence = Field(default_factory=AxisConfidence)
    SN: AxisConfidence = Field(default_factory=AxisConfidence)
    TF: AxisConfidence = Field(default_factory=AxisConfidence)
    JP: AxisConfidence = Field(default_factory=AxisConfidence)


class AxisScores(BaseModel):
    """Положение по каждой оси, 0..1. 0.5 = нейтрально/неизвестно."""
    model_config = ConfigDict(extra="forbid")

    EI: float = 0.5
    SN: float = 0.5
    TF: float = 0.5
    JP: float = 0.5


class TypeProbability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    p: float


class CoreVsRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core: List[str] = Field(default_factory=list)
    role: List[str] = Field(default_factory=list)


class AkmeVectorOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core: List[str] = Field(default_factory=list)
    unload: List[str] = Field(default_factory=list)
    environment: List[str] = Field(default_factory=list)
    risk: List[str] = Field(default_factory=list)


class SynthesisResult(BaseModel):
    """
    Финальный ответ синтезатора.
    В твоей концепции: валидный JSON и никаких текстов вне JSON.
    """
    model_config = ConfigDict(extra="forbid")

    message: str
    probabilities: List[TypeProbability] = Field(default_factory=list)
    axes_confidence: AxesConfidence | None = None
    axis_map: AxisScores = Field(default_factory=AxisScores)
    core_vs_role: CoreVsRole = Field(default_factory=CoreVsRole)
    notes: List[str] = Field(default_factory=list)
    akme_vector: AkmeVectorOut | None = None

class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_communication: Dict[str, Any]
    A: Literal["ask", "interpret", "synthesize"]
    message: str


class ConversationState(BaseModel):
    """
    Единый контракт состояния — центр всей твоей концепции.
    """
    model_config = ConfigDict(extra="forbid")
    session_id: str | None = None
    telegram_id: int | None = None
    last_saved_signals_count: int = 0
    history: List[ChatMessage] = Field(default_factory=list)
    evidence: AxisEvidence = Field(default_factory=AxisEvidence)

    validity_level: int = 4
    goals: Goals = Field(default_factory=Goals)
    notes: List[str] = Field(default_factory=list)

    # какие оси закрыты по evidence_logic
    axis_closed: Dict[Axis, bool] = Field(default_factory=lambda: {a: False for a in Axis})
    soft_axis_closed: Dict[Axis, bool] = Field(default_factory=lambda: {a: False for a in Axis})
    # метаданные управления диалогом
    priority_goal: Literal["ctx", "sig", "val", "map", "sum"] = "ctx"
    chosen_agent: Literal["diagnost", "interpreter", "synthesizer"] = "diagnost"
    reason: str = "Начало диалога"
    interpreter_used: bool = False
    dialogue_saturated: bool = False
    dialogue_completed: bool = False
    map_completed: bool = False
    map_turns: int = 0
    last_transcript: str | None = None
    awaiting_transcript_fix: bool = False
    synthesis: dict | None = None
    # NEW: подтверждён ли итог пользователем
    synthesis_confirmed: bool = False
    def add_user(self, text: str) -> None:
        self.history.append(ChatMessage(role="user", content=text))

    def add_assistant(self, text: str) -> None:
        self.history.append(ChatMessage(role="assistant", content=text))

    def add_note(self, text: str) -> None:
        if text:
            self.notes.append(text)

    def add_signals(self, signals: List[AxisSignal]) -> None:
        """
        Складывает сигналы, отсекая повторы по (axis, direction, text).

        LLM охотно переотправляет наблюдение, которое уже лежит в evidence, дословно.
        Без этого фильтра дубль накручивал бы вес закрытия оси на пустом месте.
        То же ограничение стоит в БД — uq_signal_nodup.
        """
        seen = {(s.axis, s.direction, s.text) for s in self.evidence.signals}

        for s in signals:
            key = (s.axis, s.direction, s.text)
            if key in seen:
                continue
            seen.add(key)
            self.evidence.add(s)

    def clamp_vl(self, delta: int) -> int:
        # правило: не более ±1 за шаг
        if delta > 1:
            delta = 1
        if delta < -1:
            delta = -1
        self.validity_level = max(0, min(10, self.validity_level + delta))
        return delta
