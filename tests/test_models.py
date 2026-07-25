import pytest
from pydantic import ValidationError
from core.models import ConversationState, AgentResponse

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
