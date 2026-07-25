from core.models import ConversationState, Axis
from modules.team_mirror import team_mirror_module


def test_team_mirror_adds_evidence():
    s = ConversationState()

    r = team_mirror_module(
        s,
        "В команде я обычно координирую людей и слежу за сроками, "
        "часто дожимаю задачи до конца."
    )

    assert r.activated is True

    jp_signals = s.evidence.signals_for(Axis.JP)
    assert len(jp_signals) >= 1
    assert jp_signals[0].source == "team"
    assert jp_signals[0].direction == "J"
