import pytest
from core.models import ConversationState
from core.orchestrator import Orchestrator
from tests.fakes import FakeLLM

@pytest.mark.asyncio
async def test_orchestrator_step_returns_message():
    llm = FakeLLM("Привет, это тест.")
    orch = Orchestrator(
        llm=llm,
        system_base="SYSTEM",
        diagnost_prompt="DIAG",
        interpreter_prompt="INT",
    )
    state = ConversationState()
    state, resp = await orch.step(state, "Мой ответ")
    assert "тест" in resp.message.lower()
    assert len(state.turns) >= 2
