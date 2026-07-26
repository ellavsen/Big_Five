"""Предложение подвести итог обязано быть честным о полноте карты.

Раньше здесь стояло «у меня уже сложилась целостная картина» — при трёх
неизвестных чертах из пяти это была неправда, и человек соглашался на итог,
не понимая, что половина карты это «не знаю».

Идея пользователя: не удлинять разговор всем подряд, а сказать вслух,
что картина минимальная, и дать выбрать со знанием дела.
"""
import pytest

from core.models import ConversationState, Direction, Trait, TraitSignal
from core.orchestrator import readiness_offer
from core.scoring import TRAIT_TITLES, undetermined_traits


def state_with(counts: dict[Trait, int]) -> ConversationState:
    state = ConversationState()
    state.add_signals([
        TraitSignal(trait=trait, direction=Direction.HIGH, text=f"{trait.value}-{i}")
        for trait, n in counts.items() for i in range(n)
    ])
    return state


THIN = {                       # распределение из живого второго разговора
    Trait.CONSCIENTIOUSNESS: 2,
    Trait.NEUROTICISM: 2,
    Trait.OPENNESS: 1,
    Trait.EXTRAVERSION: 1,
    Trait.AGREEABLENESS: 1,
}
FULL = {t: 3 for t in Trait}


def test_thin_map_is_called_minimal():
    offer = readiness_offer(state_with(THIN))

    assert "минимальная картина" in offer
    assert "целостная" not in offer, "именно это обещание и было неправдой"


def test_thin_map_names_what_is_missing():
    offer = readiness_offer(state_with(THIN))

    for trait in (Trait.OPENNESS, Trait.EXTRAVERSION, Trait.AGREEABLENESS):
        assert TRAIT_TITLES[trait] in offer, f"не названа непокрытая черта: {trait.value}"


def test_thin_map_recommends_continuing():
    offer = readiness_offer(state_with(THIN))

    assert "продолжить" in offer.lower()
    assert "если хочешь итог сейчас" in offer.lower(), "выбор остаётся за человеком"


def test_thin_map_explains_what_0_5_means():
    """«Посередине» — это «не знаю», а не «средне». Путать нельзя."""
    offer = readiness_offer(state_with(THIN))

    assert "не знаю" in offer
    assert "средне" in offer


def test_full_map_does_not_apologise():
    offer = readiness_offer(state_with(FULL))

    assert "минимальная" not in offer
    assert "не хватило" not in offer
    assert "картина сложилась" in offer


def test_offer_matches_the_scale():
    """Названные черты — ровно те, что шкала оставит посередине."""
    state = state_with(THIN)
    offer = readiness_offer(state)

    for trait in undetermined_traits(state.evidence):
        assert TRAIT_TITLES[trait] in offer


@pytest.mark.asyncio
async def test_offer_still_does_not_synthesize():
    """2612-правило: итог только по явному подтверждению, предложение его не заменяет."""
    from core.orchestrator import Orchestrator
    from tests.fakes import FakeLLM

    orch = Orchestrator(FakeLLM(), turn_planner_prompt="TURN", synthesizer_prompt="SYNTH")
    state = state_with(THIN)
    state.validity_level = 10

    response = await orch.step(state, "и это всё")

    if state.dialogue_saturated:
        assert response.A == "ask"
        assert state.synthesis is None
