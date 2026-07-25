from core.models import Axis, ConversationState
from core.transitions import choose_agent


def test_no_synthesis_if_axes_not_closed():
    s = ConversationState()
    s.goals.ctx = 7
    s.goals.sig = 7
    s.validity_level = 8

    # оси НЕ закрыты
    agent, reason = choose_agent(s)
    assert agent != "synthesizer"


def test_synthesizer_only_after_user_confirmation():
    """
    2612-правило: даже когда данных достаточно, синтез не начинается
    без явного подтверждения пользователем.
    """
    s = ConversationState()
    s.validity_level = 8
    s.priority_goal = "val"
    s.axis_closed = {a: True for a in Axis}
    s.soft_axis_closed = {a: True for a in Axis}
    s.interpreter_used = True

    agent, _ = choose_agent(s)
    assert agent != "synthesizer"

    s.synthesis_confirmed = True
    agent, _ = choose_agent(s)
    assert agent == "synthesizer"
