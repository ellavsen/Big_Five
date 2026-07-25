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
    assert state.synthesis["axis_map"] == {"EI": 0.3}
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
