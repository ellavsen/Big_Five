# core/validity.py
from __future__ import annotations
from typing import Dict
from dataclasses import dataclass, field
from collections import defaultdict

from core.config import (
    TRAIT_CLOSE_SCORE,
    TRAIT_DOMINANCE,
    TRAIT_MIN_SIGNALS,
    TRAIT_SOFT_SCORE,
)
from core.models import ConversationState, Direction, Trait, TraitEvidence


# =========================
# VALIDITY UPDATE
# =========================

@dataclass
class ValidityUpdate:
    delta: int
    note: str


# =========================
# TRAIT CLOSURE LOGIC
# =========================

@dataclass
class TraitWeight:
    """
    Сколько накоплено в пользу ведущего направления черты (high или low).

    До Этапа 2C черта закрывалась по флагу `direct_example` у одного сигнала, а модули
    ставили этот флаг по одному вхождению подстроки — слово «контролирую» закрывало ось.
    Теперь решает накопленный вес, число независимых наблюдений и перевес над
    противоположным направлением.
    """
    direction: Direction | None = None
    score: float = 0.0                       # сумма confidence по ведущему направлению
    opposing: float = 0.0                    # сумма confidence по противоположному
    signals: int = 0                         # наблюдений в пользу ведущего
    sources: set[str] = field(default_factory=set)
    has_direct_example: bool = False


def weigh_trait(trait: Trait, evidence: TraitEvidence) -> TraitWeight:
    signals = evidence.signals_for(trait)
    if not signals:
        return TraitWeight()

    by_direction: Dict[Direction, float] = defaultdict(float)
    for s in signals:
        by_direction[s.direction] += s.confidence

    direction = max(by_direction, key=lambda d: by_direction[d])
    leading = [s for s in signals if s.direction == direction]

    # Округление обязательно: 0.6 + 0.3 в float даёт 0.8999999999999999, и черта
    # не закрывалась бы ровно на пороговом наборе сигналов.
    return TraitWeight(
        direction=direction,
        score=round(by_direction[direction], 6),
        opposing=round(sum(v for d, v in by_direction.items() if d != direction), 6),
        signals=len(leading),
        sources={s.source for s in leading},
        has_direct_example=any(s.direct_example for s in leading),
    )


def _dominates(w: TraitWeight) -> bool:
    """Ведущее направление должно заметно перевешивать: иначе это противоречие, а не черта."""
    return w.opposing == 0.0 or w.score >= w.opposing * TRAIT_DOMINANCE


def trait_is_closed(trait: Trait, evidence: TraitEvidence) -> bool:
    """
    Жёсткое закрытие: накоплен вес, наблюдений хватает, они не из одного источника
    (либо есть настоящий эпизод), и противоположное направление не спорит.
    """
    w = weigh_trait(trait, evidence)

    return (
        w.score >= TRAIT_CLOSE_SCORE
        and w.signals >= TRAIT_MIN_SIGNALS
        and (len(w.sources) >= 2 or w.has_direct_example)
        and _dominates(w)
    )


def soft_trait_closed(trait: Trait, evidence: TraitEvidence) -> bool:
    """
    Мягкое закрытие: накопление идёт, но подтверждений ещё мало.

    Условия — подмножество жёстких, поэтому жёстко закрытая черта всегда закрыта и мягко.
    Раньше было наоборот: `soft` требовал два сигнала, а `trait_is_closed` довольствовался
    одним с `direct_example`, из-за чего «мягкое» условие оказывалось строже «жёсткого».
    """
    w = weigh_trait(trait, evidence)

    return (
        w.score >= TRAIT_SOFT_SCORE
        and w.signals >= TRAIT_MIN_SIGNALS
        and _dominates(w)
    )


# =========================
# VALIDITY HEURISTIC
# =========================

def update_validity_from_text(text: str) -> ValidityUpdate:
    """
    Мягкая эвристика:
    валидность = насыщенность материала, а не «правильность».
    """
    t = (text or "").strip().lower()

    if not t:
        return ValidityUpdate(delta=-1, note="empty_response")

    delta = 0
    notes = []

    example_markers = [
        "например", "вчера", "недавно", "однажды", "когда",
        "в проекте", "в команде", "после этого", "в тот момент"
    ]

    reflection_markers = [
        "я понял", "я поняла", "я заметила", "я осознала",
        "я вижу", "я стала"
    ]

    vague_markers = [
        "не знаю", "зависит", "по-разному", "в целом", "как-то"
    ]

    if any(m in t for m in example_markers):
        delta += 1
        notes.append("конкретный пример")

    if any(m in t for m in reflection_markers):
        delta += 1
        notes.append("рефлексия")

    if len(t) > 120:
        delta += 1
        notes.append("развёрнутый ответ")

    if any(m in t for m in vague_markers) and len(t) < 40:
        delta -= 1
        notes.append("расплывчатый ответ")

    delta = max(-1, min(1, delta))

    return ValidityUpdate(
        delta=delta,
        note="; ".join(notes) if notes else "нейтральный ответ"
    )


# =========================
# SYNTHESIS READINESS (2612)
# =========================

def _traits_with_any_signal(state: ConversationState) -> int:
    return sum(
        1 for trait in Trait
        if len(state.evidence.signals_for(trait)) >= 1
    )


def _traits_with_multiple_signals(state: ConversationState) -> int:
    return sum(
        1 for trait in Trait
        if len(state.evidence.signals_for(trait)) >= 2
    )


def is_profile_sufficient(state: ConversationState) -> bool:
    """
    КРИТЕРИЙ 2612:

    Синтез возможен, если:
    - по каждой из черт есть хотя бы одно наблюдение
    - минимум по двум чертам есть повторяемость
    - валидность говорит «материала достаточно»

    ❗ Это НЕ критерий истинности.
    Это критерий ВЫРАЗИМОСТИ КАРТЫ.

    Черт стало пять вместо четырёх (Этап 3B), поэтому критерий требует чуть больше
    материала. Это сознательно: без наблюдений про энергию и устойчивость карта
    энергии — а это и есть продукт — не собирается.
    """

    return (
        _traits_with_any_signal(state) == len(Trait)
        and _traits_with_multiple_signals(state) >= 2
        and state.validity_level >= 7
    )
