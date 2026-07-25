# core/validity.py
from __future__ import annotations
from typing import Dict
from dataclasses import dataclass, field
from collections import defaultdict

from core.config import (
    AXIS_CLOSE_SCORE,
    AXIS_DOMINANCE,
    AXIS_MIN_SIGNALS,
    AXIS_SOFT_SCORE,
)
from core.models import ConversationState, Axis, AxisEvidence


# =========================
# VALIDITY UPDATE
# =========================

@dataclass
class ValidityUpdate:
    delta: int
    note: str


# =========================
# AXIS CLOSURE LOGIC
# =========================

@dataclass
class AxisWeight:
    """
    Сколько накоплено в пользу ведущего направления оси.

    До Этапа 2C ось закрывалась по флагу `direct_example` у одного сигнала, а модули
    ставили этот флаг по одному вхождению подстроки — слово «контролирую» закрывало JP.
    Теперь решает накопленный вес, число независимых наблюдений и перевес над
    противоположным полюсом.
    """
    direction: str | None = None
    score: float = 0.0                       # сумма confidence по ведущему направлению
    opposing: float = 0.0                    # сумма confidence по всем остальным
    signals: int = 0                         # наблюдений в пользу ведущего
    sources: set[str] = field(default_factory=set)
    has_direct_example: bool = False


def weigh_axis(axis: Axis, evidence: AxisEvidence) -> AxisWeight:
    signals = evidence.for_axis(axis)
    if not signals:
        return AxisWeight()

    by_direction: Dict[str, float] = defaultdict(float)
    for s in signals:
        by_direction[s.direction] += s.confidence

    direction = max(by_direction, key=lambda d: by_direction[d])
    leading = [s for s in signals if s.direction == direction]

    # Округление обязательно: 0.6 + 0.3 в float даёт 0.8999999999999999, и ось
    # не закрывалась бы ровно на пороговом наборе сигналов.
    return AxisWeight(
        direction=direction,
        score=round(by_direction[direction], 6),
        opposing=round(sum(v for d, v in by_direction.items() if d != direction), 6),
        signals=len(leading),
        sources={s.source for s in leading},
        has_direct_example=any(s.direct_example for s in leading),
    )


def _dominates(w: AxisWeight) -> bool:
    """Ведущее направление должно заметно перевешивать: иначе это не ось, а противоречие."""
    return w.opposing == 0.0 or w.score >= w.opposing * AXIS_DOMINANCE


def axis_is_closed(axis: Axis, evidence: AxisEvidence) -> bool:
    """
    Жёсткое закрытие: накоплен вес, наблюдений хватает, они не из одного источника
    (либо есть настоящий эпизод), и противоположный полюс не спорит.
    """
    w = weigh_axis(axis, evidence)

    return (
        w.score >= AXIS_CLOSE_SCORE
        and w.signals >= AXIS_MIN_SIGNALS
        and (len(w.sources) >= 2 or w.has_direct_example)
        and _dominates(w)
    )


def soft_axis_closed(axis: Axis, evidence: AxisEvidence) -> bool:
    """
    Мягкое закрытие: накопление идёт, но подтверждений ещё мало.

    Условия — подмножество жёстких, поэтому жёстко закрытая ось всегда закрыта и мягко.
    Раньше было наоборот: `soft` требовал два сигнала, а `axis_is_closed` довольствовался
    одним с `direct_example`, из-за чего «мягкое» условие оказывалось строже «жёсткого».
    """
    w = weigh_axis(axis, evidence)

    return (
        w.score >= AXIS_SOFT_SCORE
        and w.signals >= AXIS_MIN_SIGNALS
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

def _axes_with_any_signal(state: ConversationState) -> int:
    return sum(
        1 for axis in Axis
        if len(state.evidence.signals_for(axis)) >= 1
    )


def _axes_with_multiple_signals(state: ConversationState) -> int:
    return sum(
        1 for axis in Axis
        if len(state.evidence.signals_for(axis)) >= 2
    )


def is_profile_sufficient(state: ConversationState) -> bool:
    """
    КРИТЕРИЙ 2612:

    Синтез возможен, если:
    - по всем 4 осям есть сигналы
    - минимум по 2 осям есть повторяемость
    - валидность говорит «материала достаточно»

    ❗ Это НЕ критерий истинности.
    Это критерий ВЫРАЗИМОСТИ КАРТЫ.
    """

    axes_any = _axes_with_any_signal(state)
    axes_multi = _axes_with_multiple_signals(state)

    return (
        axes_any == 4
        and axes_multi >= 2
        and state.validity_level >= 7
    )
