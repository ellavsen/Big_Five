from core.models import ConversationState, Axis, AxisSignal
from modules.synthesizer import synthesizer_module


def test_synthesizer_with_compensation():
    s = ConversationState()
    s.flags.add("compensation_pattern_detected")

    s.evidence.signals.append(
        AxisSignal(
            axis=Axis.JP,
            direction="J",
            source="team",
            text="Я всегда дожимаю сроки",
            context="team",
        )
    )

    profile = synthesizer_module(s)

    jp = profile["axes"]["J/P"]
    assert jp["status"] == "compensated"
    assert jp["dominant"] == "J"
    assert jp["confidence"] == "medium"
