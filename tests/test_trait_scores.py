"""Шкала черт: числа считает код, а не модель.

Живой диалог: модель проставила все пять черт в 0.70–0.85, включая две, где было
ровно одно наблюдение. Профиль, где выражено всё сразу, ничего не различает —
и при этом приятно читается, потому что состоит из одних сильных сторон.
"""
import pytest

from core.config import TRAIT_MIN_SIGNALS
from core.models import Direction, Trait, TraitEvidence, TraitSignal
from core.scoring import HIGH, LOW, UNKNOWN, trait_scores_from_evidence, trait_value


def evidence(*signals: TraitSignal) -> TraitEvidence:
    return TraitEvidence(signals=list(signals))


def sig(trait: Trait, direction: Direction, confidence: float = 0.6, text: str = "") -> TraitSignal:
    return TraitSignal(
        trait=trait,
        direction=direction,
        confidence=confidence,
        text=text or f"{trait.value}-{direction.value}-{confidence}",
    )


def test_no_observations_means_unknown():
    assert trait_value(Trait.OPENNESS, TraitEvidence()) == UNKNOWN


def test_single_observation_stays_unknown():
    """Главный тест. Одно наблюдение — это не «черта выражена», это «мы не знаем».

    В живом диалоге одно наблюдение по доброжелательности дало 0.70.
    """
    ev = evidence(sig(Trait.AGREEABLENESS, Direction.HIGH, 0.9))

    assert trait_value(Trait.AGREEABLENESS, ev) == UNKNOWN
    assert TRAIT_MIN_SIGNALS == 2, "тест держится на этом пороге"


def test_two_consistent_observations_read_as_expressed():
    ev = evidence(
        sig(Trait.CONSCIENTIOUSNESS, Direction.HIGH),
        sig(Trait.CONSCIENTIOUSNESS, Direction.HIGH, text="другое основание"),
    )

    assert trait_value(Trait.CONSCIENTIOUSNESS, ev) >= HIGH


def test_low_direction_goes_below_the_threshold():
    ev = evidence(
        sig(Trait.EXTRAVERSION, Direction.LOW),
        sig(Trait.EXTRAVERSION, Direction.LOW, text="второе"),
        sig(Trait.EXTRAVERSION, Direction.LOW, text="третье"),
    )

    assert trait_value(Trait.EXTRAVERSION, ev) <= LOW


def test_contradicting_observations_keep_the_trait_near_the_middle():
    """Два спорящих наблюдения — не уверенность, а неопределённость."""
    ev = evidence(
        sig(Trait.OPENNESS, Direction.HIGH),
        sig(Trait.OPENNESS, Direction.HIGH, text="второе за"),
        sig(Trait.OPENNESS, Direction.LOW, text="против"),
        sig(Trait.OPENNESS, Direction.LOW, text="ещё против"),
    )

    assert abs(trait_value(Trait.OPENNESS, ev) - UNKNOWN) < 0.1


def test_more_evidence_moves_further_from_the_middle():
    def value_for(count: int) -> float:
        return trait_value(
            Trait.NEUROTICISM,
            evidence(*[
                sig(Trait.NEUROTICISM, Direction.HIGH, text=f"наблюдение {i}")
                for i in range(count)
            ]),
        )

    assert value_for(2) < value_for(4) < value_for(8)


def test_certainty_is_never_claimed():
    """Никаких 0.0 и 1.0: это вероятности, а не диагноз."""
    many = evidence(*[
        sig(Trait.CONSCIENTIOUSNESS, Direction.HIGH, 1.0, text=f"наблюдение {i}")
        for i in range(50)
    ])

    assert 0.1 <= trait_value(Trait.CONSCIENTIOUSNESS, many) <= 0.9


@pytest.mark.parametrize("direction", list(Direction))
def test_scores_stay_in_range(direction):
    ev = evidence(*[
        sig(t, direction, 0.9, text=f"{t.value}-{i}")
        for t in Trait for i in range(5)
    ])

    for value in trait_scores_from_evidence(ev).model_dump().values():
        assert 0.0 <= value <= 1.0


def test_the_live_conversation_would_not_be_all_high():
    """Воспроизводит распределение наблюдений из живого диалога.

    Было: 4 добросовестность, 3 экстраверсия, 3 реактивность, 1 доброжелательность,
    1 открытость — и все пять черт вышли высокими.
    """
    counts = {
        Trait.CONSCIENTIOUSNESS: 4,
        Trait.EXTRAVERSION: 3,
        Trait.NEUROTICISM: 3,
        Trait.AGREEABLENESS: 1,
        Trait.OPENNESS: 1,
    }
    ev = evidence(*[
        sig(trait, Direction.HIGH, text=f"{trait.value}-{i}")
        for trait, n in counts.items() for i in range(n)
    ])

    scores = trait_scores_from_evidence(ev)

    assert scores.agreeableness == UNKNOWN, "одно наблюдение не делает черту выраженной"
    assert scores.openness == UNKNOWN
    assert scores.conscientiousness >= HIGH
    assert scores.extraversion >= HIGH

    expressed = sum(1 for v in scores.model_dump().values() if v >= HIGH)
    assert expressed < 5, "профиль, где выражено всё сразу, ничего не различает"
