from __future__ import annotations
from dataclasses import dataclass
from collections import Counter

from core.models import ConversationState, Axis


# =========================
# Внутренние структуры
# =========================

@dataclass
class AxisSummary:
    axis: Axis
    dominant: str | None
    status: str          # core | compensated | boundary | unknown
    confidence: str      # low | medium | high
    rationale: str


# =========================
# ВСПОМОГАТЕЛЬНАЯ ЛОГИКА
# =========================

def _axis_direction_counts(state: ConversationState, axis: Axis) -> Counter:
    signals = state.evidence.signals_for(axis)
    return Counter(s.direction for s in signals)


def _axis_sources(state: ConversationState, axis: Axis) -> set[str]:
    return {s.source for s in state.evidence.signals_for(axis)}


def _has_compensation(state: ConversationState) -> bool:
    # признаки компенсации ставят детерминированные модули: note вида "compensation:control"
    return any(n.startswith("compensation:") for n in state.notes)


# =========================
# СИНТЕЗ ОСИ
# =========================

def synthesize_axis(state: ConversationState, axis: Axis) -> AxisSummary:
    signals = state.evidence.signals_for(axis)

    if not signals:
        return AxisSummary(
            axis=axis,
            dominant=None,
            status="unknown",
            confidence="low",
            rationale="Недостаточно наблюдаемых сигналов."
        )

    counts = _axis_direction_counts(state, axis)

    if len(counts) == 1:
        dominant = next(iter(counts))
        sources = _axis_sources(state, axis)

        # Если есть компенсация и источники не энергетические → осторожно
        if _has_compensation(state) and "energy" not in sources:
            return AxisSummary(
                axis=axis,
                dominant=dominant,
                status="compensated",
                confidence="medium",
                rationale=(
                    "Поведение по оси проявляется устойчиво, "
                    "но есть признаки компенсаторного характера "
                    "и повышенной энергозатраты."
                )
            )

        return AxisSummary(
            axis=axis,
            dominant=dominant,
            status="core",
            confidence="high" if "energy" in sources else "medium",
            rationale="Сигналы по оси согласованы в разных контекстах."
        )

    # Противоречивые направления
    return AxisSummary(
        axis=axis,
        dominant=None,
        status="boundary",
        confidence="low",
        rationale=(
            "По оси проявляются разнонаправленные сигналы "
            "в разных ситуациях — возможен пограничный профиль."
        )
    )


# =========================
# ГЛАВНЫЙ SYNTHESIZER
# =========================

def synthesizer_module(state: ConversationState) -> dict:
    """
    Возвращает структурированный профиль для интерпретации пользователю.
    НИЧЕГО не меняет в state.
    """

    axis_summaries = {
        axis.value: synthesize_axis(state, axis)
        for axis in Axis
    }

    # Уровень профиля
    if state.validity_level >= 7:
        profile_depth = "глубокий"
    elif state.validity_level >= 5:
        profile_depth = "расширенный"
    else:
        profile_depth = "базовый"

    return {
        "profile_depth": profile_depth,
        "axes": {
            axis: {
                "dominant": summary.dominant,
                "status": summary.status,
                "confidence": summary.confidence,
                "rationale": summary.rationale,
            }
            for axis, summary in axis_summaries.items()
        },
        "has_compensation": _has_compensation(state),
        "notes": state.notes,
    }
