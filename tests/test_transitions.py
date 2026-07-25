from core.models import ConversationState, Axis, AxisSignal
from core.transitions import choose_agent

def test_no_synthesis_if_axes_not_closed():
    s = ConversationState()
    s.goals.ctx = 7
    s.goals.sig = 7
    s.validity_level = 8

    # оси НЕ закрыты
    agent, reason = choose_agent(s)
    assert agent != "synthesizer"

def test_synthesis_only_when_ready():
    s = ConversationState()
    s.goals.ctx = 7
    s.goals.sig = 7
    s.validity_level = 8

    # здесь ты добавишь all_axes_closed через evidence — в зависимости от твоей версии choose_agent
    # тест допишем после того, как код all_axes_closed точно у тебя стоит
