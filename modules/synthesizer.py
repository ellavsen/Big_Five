from __future__ import annotations
from dataclasses import dataclass
from collections import Counter

from core.models import ConversationState, Direction, Trait


# =========================
# Внутренние структуры
# =========================

@dataclass
class TraitSummary:
    trait: Trait
    dominant: Direction | None
    status: str          # core | compensated | boundary | unknown
    confidence: str      # low | medium | high
    rationale: str


# =========================
# ВСПОМОГАТЕЛЬНАЯ ЛОГИКА
# =========================

def _trait_direction_counts(state: ConversationState, trait: Trait) -> Counter:
    signals = state.evidence.signals_for(trait)
    return Counter(s.direction for s in signals)


def _trait_sources(state: ConversationState, trait: Trait) -> set[str]:
    return {s.source for s in state.evidence.signals_for(trait)}


def _has_compensation(state: ConversationState) -> bool:
    # признаки компенсации ставят детерминированные модули: note вида "compensation:control"
    return any(n.startswith("compensation:") for n in state.notes)


# =========================
# СИНТЕЗ ЧЕРТЫ
# =========================

def synthesize_trait(state: ConversationState, trait: Trait) -> TraitSummary:
    signals = state.evidence.signals_for(trait)

    if not signals:
        return TraitSummary(
            trait=trait,
            dominant=None,
            status="unknown",
            confidence="low",
            rationale="Недостаточно наблюдаемых сигналов."
        )

    counts = _trait_direction_counts(state, trait)

    if len(counts) == 1:
        dominant = next(iter(counts))
        sources = _trait_sources(state, trait)

        # Если есть компенсация и источники не энергетические → осторожно
        if _has_compensation(state) and "energy" not in sources:
            return TraitSummary(
                trait=trait,
                dominant=dominant,
                status="compensated",
                confidence="medium",
                rationale=(
                    "Черта проявляется устойчиво, "
                    "но есть признаки компенсаторного характера "
                    "и повышенной энергозатраты."
                )
            )

        return TraitSummary(
            trait=trait,
            dominant=dominant,
            status="core",
            confidence="high" if "energy" in sources else "medium",
            rationale="Наблюдения по черте согласованы в разных контекстах."
        )

    # Противоречивые направления
    return TraitSummary(
        trait=trait,
        dominant=None,
        status="boundary",
        confidence="low",
        rationale=(
            "По черте проявляются разнонаправленные наблюдения "
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

    trait_summaries = {
        trait.value: synthesize_trait(state, trait)
        for trait in Trait
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
        "traits": {
            trait: {
                "dominant": summary.dominant.value if summary.dominant else None,
                "status": summary.status,
                "confidence": summary.confidence,
                "rationale": summary.rationale,
            }
            for trait, summary in trait_summaries.items()
        },
        "has_compensation": _has_compensation(state),
        "notes": state.notes,
    }
