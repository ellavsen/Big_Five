# core/models.py
from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator

class Trait(str, Enum):
    """
    Ядро оценки — Big Five (OCEAN). Не биполярные оси MBTI, а измеримые черты:
    у каждой есть выраженность, а не «сторона».

    Neuroticism не имеет соответствия в MBTI, и именно он отвечает за реактивность
    на стресс, истощение и восстановление — то есть за заявленное ядро продукта.
    Пока черт было четыре, наблюдения про энергию класть было некуда.
    """
    OPENNESS = "openness"
    CONSCIENTIOUSNESS = "conscientiousness"
    EXTRAVERSION = "extraversion"
    AGREEABLENESS = "agreeableness"
    NEUROTICISM = "neuroticism"


class Direction(str, Enum):
    """Черта выражена сильно или слабо. Заменила полюса MBTI (E/I, S/N, T/F, J/P)."""
    HIGH = "high"
    LOW = "low"


SignalSource = Literal["llm", "user", "energy", "module", "direct_example"]


class TraitSignal(BaseModel):
    """
    Одно наблюдение по одной черте.
    confidence — насколько уверенно оно поддерживает direction (0..1).
    """
    model_config = ConfigDict(extra="forbid")

    trait: Trait
    direction: Direction
    text: str = Field(..., description="Короткое основание: что именно в ответе дало сигнал")
    source: SignalSource = "llm"
    # ge/le нельзя: strict-схема structured outputs не поддерживает minimum/maximum.
    # Диапазон держим валидатором — модель, вышедшую за 0..1, подрезаем, а не роняем ход.
    confidence: float = 0.6
    direct_example: bool = False

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class TraitEvidence(BaseModel):
    """
    Склад всех наблюдений по всем чертам.
    """
    model_config = ConfigDict(extra="forbid")

    signals: List[TraitSignal] = Field(default_factory=list)

    def add(self, sig: TraitSignal) -> None:
        self.signals.append(sig)

    def signals_for(self, trait: Trait) -> List[TraitSignal]:
        return [s for s in self.signals if s.trait == trait]


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
    trait_signals: List[TraitSignal] = []


# =========================
# Форма ответа синтезатора.
#
# Все контейнеры здесь — с фиксированными ключами. Это требование strict-схемы
# structured outputs: открытые словари (черта → значение как additionalProperties)
# API не принимает. Поэтому черты перечислены полями, а probabilities — списком пар.
# Значения по умолчанию нужны только fallback-пути в core/llm.py: в самой схеме
# все поля обязательны, модель обязана вернуть их целиком.
# =========================

class TraitConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence: float = 0.0  # 0.0–1.0
    stability: Literal["устойчивая", "пограничная"] = "пограничная"


class TraitsConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    openness: TraitConfidence = Field(default_factory=TraitConfidence)
    conscientiousness: TraitConfidence = Field(default_factory=TraitConfidence)
    extraversion: TraitConfidence = Field(default_factory=TraitConfidence)
    agreeableness: TraitConfidence = Field(default_factory=TraitConfidence)
    neuroticism: TraitConfidence = Field(default_factory=TraitConfidence)


class TraitScores(BaseModel):
    """
    Выраженность каждой черты, 0..1. 1.0 = черта выражена сильно, 0.0 = слабо,
    0.5 = нейтрально либо данных не хватает.

    Внимание к `neuroticism`: высокое значение = высокая реактивность на стресс,
    низкое = эмоциональная устойчивость. Это не «плохо/хорошо», а профиль нагрузки.
    """
    model_config = ConfigDict(extra="forbid")

    openness: float = 0.5
    conscientiousness: float = 0.5
    extraversion: float = 0.5
    agreeableness: float = 0.5
    neuroticism: float = 0.5


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
    # MBTI-типы: популярная обёртка, выводимая из черт. Не ядро оценки.
    probabilities: List[TypeProbability] = Field(default_factory=list)
    traits_confidence: TraitsConfidence | None = None
    trait_scores: TraitScores = Field(default_factory=TraitScores)
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
    evidence: TraitEvidence = Field(default_factory=TraitEvidence)

    validity_level: int = 4
    goals: Goals = Field(default_factory=Goals)
    notes: List[str] = Field(default_factory=list)

    # какие черты набрали достаточно наблюдений
    trait_closed: Dict[Trait, bool] = Field(default_factory=lambda: {t: False for t in Trait})
    soft_trait_closed: Dict[Trait, bool] = Field(default_factory=lambda: {t: False for t in Trait})
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

    def add_signals(self, signals: List[TraitSignal]) -> None:
        """
        Складывает наблюдения, отсекая повторы по (trait, direction, text).

        LLM охотно переотправляет наблюдение, которое уже лежит в evidence, дословно.
        Без этого фильтра дубль накручивал бы вес закрытия черты на пустом месте.
        То же ограничение стоит в БД — uq_signal_nodup.
        """
        seen = {(s.trait, s.direction, s.text) for s in self.evidence.signals}

        for s in signals:
            key = (s.trait, s.direction, s.text)
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
