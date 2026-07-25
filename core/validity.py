# core/validity.py
from __future__ import annotations
from typing import Dict
from dataclasses import dataclass
from collections import defaultdict

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

def axis_is_closed(axis: Axis, evidence: AxisEvidence) -> bool:
    """
    Жёсткое закрытие оси:
    - прямой пример
    - или ≥2 источников
    - или ≥3 повторений одного направления
    """
    signals = evidence.for_axis(axis)
    if not signals:
        return False

    if any(s.direct_example for s in signals):
        return True

    sources = {s.source for s in signals}
    if len(sources) >= 2:
        return True

    dir_count: Dict[str, int] = defaultdict(int)
    for s in signals:
        dir_count[s.direction] += 1

    return any(count >= 3 for count in dir_count.values())


def soft_axis_closed(axis: Axis, evidence: AxisEvidence) -> bool:
    """
    Мягкое закрытие оси:
    - ≥2 согласованных сигнала
    - или прямой + косвенный пример
    """
    signals = evidence.for_axis(axis)

    if len(signals) >= 2:
        return True

    direct = [s for s in signals if s.direct_example]
    indirect = [s for s in signals if not s.direct_example]

    return bool(direct and indirect)


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
