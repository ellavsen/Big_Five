import pytest

from core.models import ConversationState, Direction, Trait, TraitSignal
from core.validity import soft_trait_closed, trait_is_closed, weigh_trait
from modules.registry import MODULES

T = Trait.CONSCIENTIOUSNESS


def _sig(direction: Direction, text: str, source: str = "llm",
         confidence: float = 0.6, direct: bool = False):
    return TraitSignal(trait=T, direction=direction, text=text,
                       source=source, confidence=confidence, direct_example=direct)


def _evidence(*signals) -> ConversationState:
    s = ConversationState()
    s.add_signals(list(signals))
    return s


# --- главный критерий этапа 2C ---

@pytest.mark.parametrize("word", ["хочется", "расслабляюсь", "контролирую", "мне важно"])
def test_single_word_does_not_close_a_trait(word):
    """
    Было: модуль ставил direct_example=True по одному вхождению подстроки,
    а закрытие срабатывало по этому флагу. Слово «контролирую» закрывало черту.
    """
    state = ConversationState()
    for module in MODULES:
        module(state, word)

    assert any(state.evidence.signals), "наблюдение всё же должно появиться — просто слабое"
    assert [t for t in Trait if trait_is_closed(t, state.evidence)] == []


def test_one_reply_no_longer_closes_several_traits():
    state = ConversationState()
    for module in MODULES:
        module(state, "мне важно, чтобы всем было спокойно, поэтому я всё контролирую, а потом расслабляюсь")

    assert [t for t in Trait if trait_is_closed(t, state.evidence)] == []


# --- накопление ---

def test_two_confirmations_from_different_sources_close_the_trait():
    state = _evidence(
        _sig(Direction.HIGH, "планирует день заранее", source="llm"),
        _sig(Direction.HIGH, "настойчивость и контроль процесса", source="module", confidence=0.3),
    )
    assert trait_is_closed(T, state.evidence)


def test_score_exactly_on_the_threshold_closes_the_trait():
    """
    Регресс на арифметику: 0.6 + 0.3 в float даёт 0.8999999999999999,
    и черта не закрывалась ровно на пороговом наборе наблюдений.
    """
    state = _evidence(
        _sig(Direction.HIGH, "первое наблюдение", source="llm", confidence=0.6),
        _sig(Direction.HIGH, "второе наблюдение", source="module", confidence=0.3),
    )
    assert weigh_trait(T, state.evidence).score == 0.9
    assert trait_is_closed(T, state.evidence)


def test_single_source_without_episode_is_not_enough():
    """Два наблюдения от одной только LLM без конкретного эпизода — ещё не закрытие."""
    state = _evidence(
        _sig(Direction.HIGH, "планирует день заранее"),
        _sig(Direction.HIGH, "не любит менять планы"),
    )
    assert not trait_is_closed(T, state.evidence)


def test_single_source_with_real_episode_is_enough():
    state = _evidence(
        _sig(Direction.HIGH, "планирует день заранее"),
        _sig(Direction.HIGH, "вчера довела релиз до конца сама", direct=True),
    )
    assert trait_is_closed(T, state.evidence)


def test_contradiction_is_not_a_closed_trait():
    """Разнонаправленные наблюдения — это пограничный профиль, а не выраженная черта."""
    state = _evidence(
        _sig(Direction.HIGH, "планирует заранее", direct=True),
        _sig(Direction.LOW, "легко меняет планы на ходу", direct=True),
    )
    assert not trait_is_closed(T, state.evidence)
    assert not soft_trait_closed(T, state.evidence)


def test_weight_reports_leading_direction_and_opposition():
    state = _evidence(
        _sig(Direction.HIGH, "планирует заранее"),
        _sig(Direction.HIGH, "держит структуру за других"),
        _sig(Direction.LOW, "иногда бросает начатое", confidence=0.3),
    )
    w = weigh_trait(T, state.evidence)

    assert w.direction is Direction.HIGH
    assert w.score == pytest.approx(1.2)
    assert w.opposing == pytest.approx(0.3)
    assert w.signals == 2


# --- инвариант ---

@pytest.mark.parametrize("signals", [
    [_sig(Direction.HIGH, "a"), _sig(Direction.HIGH, "b", source="module", confidence=0.3)],
    [_sig(Direction.HIGH, "a"), _sig(Direction.HIGH, "b", direct=True)],
    [_sig(Direction.HIGH, "a")],
    [_sig(Direction.HIGH, "a"), _sig(Direction.LOW, "b")],
    [_sig(Direction.HIGH, "a", confidence=0.25, source="module"),
     _sig(Direction.HIGH, "b", confidence=0.25, source="energy")],
])
def test_hard_closed_always_implies_soft_closed(signals):
    """
    Раньше было наоборот: soft требовал два наблюдения, а жёсткое закрытие
    довольствовалось одним с direct_example — «мягкое» условие было строже.
    """
    state = _evidence(*signals)

    if trait_is_closed(T, state.evidence):
        assert soft_trait_closed(T, state.evidence)


def test_empty_trait_is_closed_by_nothing():
    state = ConversationState()
    assert not trait_is_closed(T, state.evidence)
    assert not soft_trait_closed(T, state.evidence)
    assert weigh_trait(T, state.evidence).direction is None


# --- дубли ---

def test_repeated_signal_does_not_inflate_the_trait():
    """LLM переотправляет уже собранное наблюдение дословно — вес расти не должен."""
    state = ConversationState()
    for _ in range(3):
        state.add_signals([_sig(Direction.HIGH, "планирует день заранее", direct=True)])

    assert len(state.evidence.signals) == 1
    assert not trait_is_closed(T, state.evidence)


def test_different_observations_are_kept():
    state = _evidence(
        _sig(Direction.HIGH, "планирует день заранее"),
        _sig(Direction.HIGH, "держит структуру за других"),
    )
    assert len(state.evidence.signals) == 2
