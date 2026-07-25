# core/models.py
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Literal
from pydantic import BaseModel, Field, ConfigDict

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
    confidence: float = Field(0.6, ge=0.0, le=1.0)
    direct_example: bool = False


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
    A: Literal["ask", "interpret"]
    message: str
    axis_signals: List[AxisSignal] = []

class AxisConfidence(BaseModel):
    confidence: float  # 0.0–1.0
    stability: Literal["устойчивая", "пограничная"]

class SynthesisResult(BaseModel):
    """
    Финальный ответ синтезатора.
    В твоей концепции: валидный JSON и никаких текстов вне JSON.
    """
    # форма ровно та, что описана в prompts/synthesizer.md:
    # {"EI": {"confidence": 0.72, "stability": "устойчивая"}}
    axes_confidence: dict[str, AxisConfidence] | None = None
    model_config = ConfigDict(extra="forbid")
    
    message: str
    probabilities: Dict[str, float] = Field(default_factory=dict)
    axis_map: Dict[str, float] = Field(default_factory=dict)
    core_vs_role: Dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = []
    akme_vector: dict | None = None

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
        for s in signals:
            self.evidence.add(s)

    def clamp_vl(self, delta: int) -> int:
        # правило: не более ±1 за шаг
        if delta > 1:
            delta = 1
        if delta < -1:
            delta = -1
        self.validity_level = max(0, min(10, self.validity_level + delta))
        return delta
