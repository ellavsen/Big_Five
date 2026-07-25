from core.models import ConversationState, Trait
from core.transitions import choose_agent


def test_no_synthesis_if_traits_not_closed():
    s = ConversationState()
    s.goals.ctx = 7
    s.goals.sig = 7
    s.validity_level = 8

    # черты НЕ закрыты
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
    s.trait_closed = {t: True for t in Trait}
    s.soft_trait_closed = {t: True for t in Trait}
    s.interpreter_used = True

    agent, _ = choose_agent(s)
    assert agent != "synthesizer"

    s.synthesis_confirmed = True
    agent, _ = choose_agent(s)
    assert agent == "synthesizer"
