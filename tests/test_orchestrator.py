import json

import pytest

from core.models import Axis, AxisSignal, ConversationState, SynthesisResult
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
    одинарные кавычки, True/False, Axis.EI. Модель должна получать JSON.
    """
    orch = _orch(FakeLLM())
    state = ConversationState()
    state.add_signals([
        AxisSignal(axis=Axis.EI, direction="I", text="пример", source="llm"),
    ])
    state.add_note("energy:depletion")
    await orch.step(state, "вчера был тяжёлый день, я устала")

    for prompt in (orch._build_turn_prompt(state), orch._build_synthesis_prompt(state)):
        payload = prompt.split("\n", 1)[1].strip().splitlines()[-1]
        ctx = json.loads(payload)  # упадёт на repr-е
        assert ctx["axis_closed"].keys() == {"EI", "SN", "TF", "JP"}


@pytest.mark.asyncio
async def test_synthesis_saves_structured_dict():
    """
    Регресс: оркестратор пытался распарсить JSON из result.message (связного текста)
    и терял axis_map / core_vs_role / akme_vector — /akme получал пустую структуру.
    """
    synthesis = SynthesisResult(
        message="Тёплый связный текст",
        axis_map={"EI": 0.3},
        core_vs_role={"core": ["анализ"], "role": ["контроль"]},
        akme_vector={"unload": ["избыточный контроль"]},
    )
    orch = _orch(FakeLLM(synthesis=synthesis))

    state = ConversationState()
    state.synthesis_confirmed = True

    resp = await orch.step(state, "давай итог")

    assert resp.A == "synthesize"
    assert resp.message == "Тёплый связный текст"
    # оси с фиксированными ключами: незаданные приходят нейтральными 0.5
    assert state.synthesis["axis_map"] == {"EI": 0.3, "SN": 0.5, "TF": 0.5, "JP": 0.5}
    assert state.synthesis["core_vs_role"]["role"] == ["контроль"]
    assert state.dialogue_completed is True


@pytest.mark.asyncio
async def test_saturated_dialogue_asks_for_confirmation_instead_of_synthesizing():
    """2612: карта выразима → предлагаем итог, но не синтезируем сами."""
    orch = _orch(FakeLLM())

    state = ConversationState()
    state.validity_level = 8
    for axis, direction in ((Axis.EI, "I"), (Axis.SN, "S"), (Axis.TF, "F"), (Axis.JP, "J")):
        state.evidence.add(AxisSignal(axis=axis, direction=direction, source="llm", text="раз"))
        state.evidence.add(AxisSignal(axis=axis, direction=direction, source="llm", text="два"))

    resp = await orch.step(state, "")

    assert state.dialogue_saturated is True
    assert resp.A == "ask"
    assert "итог" in resp.message.lower()
    assert state.synthesis is None
