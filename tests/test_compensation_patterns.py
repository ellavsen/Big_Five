from core.models import ConversationState, Direction, Trait
from modules.compensation_patterns import compensation_patterns


def test_compensation_adds_note_and_signal():
    s = ConversationState()

    compensation_patterns(
        s,
        "Мне приходится постоянно всё контролировать, иначе без меня команда разваливается.",
    )

    assert "compensation:control" in s.notes

    signals = s.evidence.signals_for(Trait.CONSCIENTIOUSNESS)
    assert len(signals) == 1
    assert signals[0].direction is Direction.HIGH


def test_no_compensation_without_markers():
    s = ConversationState()

    compensation_patterns(s, "Вчера гуляли в парке, было спокойно.")

    assert s.notes == []
    assert s.evidence.signals == []
