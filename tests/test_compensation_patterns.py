from core.models import Axis, ConversationState
from modules.compensation_patterns import compensation_patterns


def test_compensation_adds_note_and_signal():
    s = ConversationState()

    compensation_patterns(
        s,
        "Мне приходится постоянно всё контролировать, иначе без меня команда разваливается.",
    )

    assert "compensation:control" in s.notes

    jp = s.evidence.signals_for(Axis.JP)
    assert len(jp) == 1
    assert jp[0].direction == "J"


def test_no_compensation_without_markers():
    s = ConversationState()

    compensation_patterns(s, "Вчера гуляли в парке, было спокойно.")

    assert s.notes == []
    assert s.evidence.signals == []
