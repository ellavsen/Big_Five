from core.models import ConversationState, Axis, AxisSignal
from core.goals_updater import update_signal_goal, update_validation_goal

def test_goals_update_with_closed_axes():
    s = ConversationState()

    # закрываем EI двумя источниками
    s.evidence.signals.append(AxisSignal(axis=Axis.EI, direction="I", source="energy", text="созвоны выматывают", context="work"))
    s.evidence.signals.append(AxisSignal(axis=Axis.EI, direction="I", source="team", text="в команде быстро устаю", context="team"))

    update_signal_goal(s)
    update_validation_goal(s)

    assert s.goals.sig >= 2
    assert s.goals.val >= 4
