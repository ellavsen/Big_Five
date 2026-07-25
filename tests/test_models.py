import pytest
from pydantic import ValidationError
from core.models import AgentResponse, ConversationState, SynthesisResult

def test_state_defaults():
    s = ConversationState()
    assert s.validity_level == 4
    assert s.goals is not None

def test_agent_response_schema_ok():
    resp = AgentResponse(
        agent_communication={"G":"ctx3-sig1-val1-map0-sum0","VL":4,"PG":"ctx","AG":"diagnost","R":"x"},
        A="ask",
        message="Привет"
    )
    assert resp.A == "ask"

def test_agent_response_forbid_extra():
    with pytest.raises(ValidationError):
        AgentResponse(
            agent_communication={"G":"x","VL":4,"PG":"ctx","AG":"diagnost","R":"x"},
            A="ask",
            message="ok",
            extra_field="boom"  # должно упасть
        )


def test_synthesis_result_accepts_axes_confidence_from_prompt():
    """
    Регресс: prompts/synthesizer.md велит вернуть axes_confidence как объекты
    {confidence, stability}, а модель ждала число — синтез падал ValidationError
    ровно после нажатия «✅ Подвести итог».
    """
    result = SynthesisResult.model_validate({
        "message": "тёплый текст",
        "axes_confidence": {"EI": {"confidence": 0.72, "stability": "устойчивая"}},
    })

    assert result.axes_confidence.EI.confidence == 0.72
    assert result.axes_confidence.EI.stability == "устойчивая"
