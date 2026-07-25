from core.models import Axis, AxisSignal, ConversationState
from modules.synthesizer import synthesizer_module


def _state_with_jp_signal() -> ConversationState:
    s = ConversationState()
    s.evidence.add(
        AxisSignal(axis=Axis.JP, direction="J", source="module", text="дожимаю сроки")
    )
    return s


def test_axis_status_core_without_compensation():
    profile = synthesizer_module(_state_with_jp_signal())

    assert profile["has_compensation"] is False
    assert profile["axes"]["JP"]["status"] == "core"
    assert profile["axes"]["JP"]["dominant"] == "J"


def test_axis_status_compensated_when_module_flagged_compensation():
    """
    Регресс: признак компенсации читался из несуществующего state.flags
    и модуль падал AttributeError. Источник — notes, куда пишут детерминированные модули.
    """
    s = _state_with_jp_signal()
    s.add_note("compensation:control")

    profile = synthesizer_module(s)

    assert profile["has_compensation"] is True
    assert profile["axes"]["JP"]["status"] == "compensated"
    assert profile["axes"]["JP"]["dominant"] == "J"


def test_axis_without_signals_is_unknown():
    profile = synthesizer_module(ConversationState())

    assert profile["axes"]["EI"]["status"] == "unknown"
    assert profile["axes"]["EI"]["dominant"] is None


def test_conflicting_directions_give_boundary():
    s = ConversationState()
    s.evidence.add(AxisSignal(axis=Axis.EI, direction="I", source="module", text="устаю от созвонов"))
    s.evidence.add(AxisSignal(axis=Axis.EI, direction="E", source="llm", text="люблю обсуждать вслух"))

    profile = synthesizer_module(s)

    assert profile["axes"]["EI"]["status"] == "boundary"
    assert profile["axes"]["EI"]["dominant"] is None
