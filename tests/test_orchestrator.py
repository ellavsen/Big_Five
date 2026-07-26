import json

import pytest

from core.coverage import plan_turn_goal
from core.models import ConversationState, Direction, SynthesisResult, Trait, TraitSignal
from core.orchestrator import Orchestrator
from tests.fakes import FakeLLM


def _orch(llm: FakeLLM) -> Orchestrator:
    return Orchestrator(
        llm=llm,
        turn_planner_prompt="TURN",
        synthesizer_prompt="SYNTH",
    )


@pytest.mark.asyncio
async def test_step_returns_message_and_writes_history():
    orch = _orch(FakeLLM("Привет, это тест."))
    state = ConversationState()

    resp = await orch.step(state, "Мой ответ")

    assert resp.A == "ask"
    assert "тест" in resp.message.lower()
    assert len(state.history) >= 2


@pytest.mark.asyncio
async def test_prompt_context_is_valid_json():
    """
    Состояние уходило в промпт через f-string, то есть Python-repr:
    одинарные кавычки, True/False, Trait.EXTRAVERSION. Модель должна получать JSON.
    """
    orch = _orch(FakeLLM())
    state = ConversationState()
    state.add_signals([
        TraitSignal(trait=Trait.EXTRAVERSION, direction=Direction.LOW, text="пример", source="llm"),
    ])
    state.add_note("energy:depletion")
    await orch.step(state, "вчера был тяжёлый день, я устала")

    turn_prompt = orch._build_turn_prompt(state, plan_turn_goal(state))
    for prompt in (turn_prompt, orch._build_synthesis_prompt(state)):
        payload = prompt.split("\n", 1)[1].strip().splitlines()[-1]
        ctx = json.loads(payload)  # упадёт на repr-е
        assert set(ctx["trait_closed"]) == {t.value for t in Trait}


@pytest.mark.asyncio
async def test_synthesis_saves_structured_dict():
    """
    Регресс: оркестратор пытался распарсить JSON из result.message (связного текста)
    и терял trait_scores / core_vs_role / akme_vector — /akme получал пустую структуру.
    """
    synthesis = SynthesisResult(
        message="Тёплый связный текст",
        trait_scores={"extraversion": 0.3},
        core_vs_role={"core": ["анализ"], "role": ["контроль"]},
        akme_vector={"unload": ["избыточный контроль"]},
    )
    orch = _orch(FakeLLM(synthesis=synthesis))

    state = ConversationState()
    state.synthesis_confirmed = True

    resp = await orch.step(state, "давай итог")

    assert resp.A == "synthesize"
    assert resp.message == "Тёплый связный текст"
    assert state.synthesis["core_vs_role"]["role"] == ["контроль"]
    assert state.synthesis["akme_vector"]["unload"] == ["избыточный контроль"]
    assert state.dialogue_completed is True

    # А вот числа профиля от модели не берутся: она прислала extraversion 0.3,
    # но наблюдений в состоянии нет — значит 0.5, «данных не хватило».
    assert state.synthesis["trait_scores"]["extraversion"] == 0.5
    assert state.synthesis["trait_scores"]["neuroticism"] == 0.5


@pytest.mark.asyncio
async def test_saturated_dialogue_asks_for_confirmation_instead_of_synthesizing():
    """2612: карта выразима → предлагаем итог, но не синтезируем сами."""
    orch = _orch(FakeLLM())

    state = ConversationState()
    state.validity_level = 8
    for trait in Trait:
        state.evidence.add(TraitSignal(trait=trait, direction=Direction.HIGH, source="llm", text="раз"))
        state.evidence.add(TraitSignal(trait=trait, direction=Direction.HIGH, source="llm", text="два"))

    resp = await orch.step(state, "")

    assert state.dialogue_saturated is True
    assert resp.A == "ask"
    assert "итог" in resp.message.lower()
    assert state.synthesis is None
