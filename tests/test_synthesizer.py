from core.models import ConversationState, Direction, Trait, TraitSignal
from modules.synthesizer import synthesizer_module

T = Trait.CONSCIENTIOUSNESS


def _state_with_signal() -> ConversationState:
    s = ConversationState()
    s.evidence.add(
        TraitSignal(trait=T, direction=Direction.HIGH, source="module", text="дожимаю сроки")
    )
    return s


def test_trait_status_core_without_compensation():
    profile = synthesizer_module(_state_with_signal())

    assert profile["has_compensation"] is False
    assert profile["traits"][T.value]["status"] == "core"
    assert profile["traits"][T.value]["dominant"] == "high"


def test_trait_status_compensated_when_module_flagged_compensation():
    """
    Регресс: признак компенсации читался из несуществующего state.flags
    и модуль падал AttributeError. Источник — notes, куда пишут детерминированные модули.
    """
    s = _state_with_signal()
    s.add_note("compensation:control")

    profile = synthesizer_module(s)

    assert profile["has_compensation"] is True
    assert profile["traits"][T.value]["status"] == "compensated"


def test_trait_without_signals_is_unknown():
    profile = synthesizer_module(ConversationState())

    assert profile["traits"][Trait.EXTRAVERSION.value]["status"] == "unknown"
    assert profile["traits"][Trait.EXTRAVERSION.value]["dominant"] is None


def test_conflicting_directions_give_boundary():
    s = ConversationState()
    e = Trait.EXTRAVERSION
    s.evidence.add(TraitSignal(trait=e, direction=Direction.LOW, source="module", text="устаю от созвонов"))
    s.evidence.add(TraitSignal(trait=e, direction=Direction.HIGH, source="llm", text="люблю обсуждать вслух"))

    profile = synthesizer_module(s)

    assert profile["traits"][e.value]["status"] == "boundary"
    assert profile["traits"][e.value]["dominant"] is None
