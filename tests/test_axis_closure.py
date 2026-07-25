import pytest

from core.models import Axis, AxisSignal, ConversationState
from core.validity import axis_is_closed, soft_axis_closed, weigh_axis
from modules.registry import MODULES


def _sig(direction: str, text: str, source: str = "llm", confidence: float = 0.6, direct: bool = False):
    return AxisSignal(axis=Axis.JP, direction=direction, text=text,
                      source=source, confidence=confidence, direct_example=direct)


def _evidence(*signals) -> ConversationState:
    s = ConversationState()
    s.add_signals(list(signals))
    return s


# --- главный критерий этапа ---

@pytest.mark.parametrize("word", ["хочется", "расслабляюсь", "контролирую", "мне важно"])
def test_single_word_does_not_close_an_axis(word):
    """
    Было: модуль ставил direct_example=True по одному вхождению подстроки,
    а axis_is_closed закрывал ось по этому флагу. Слово «контролирую» закрывало JP.
    """
    state = ConversationState()
    for module in MODULES:
        module(state, word)

    assert any(state.evidence.signals), "сигнал всё же должен появиться — просто слабый"
    assert [a for a in Axis if axis_is_closed(a, state.evidence)] == []


def test_one_reply_no_longer_closes_three_axes():
    state = ConversationState()
    for module in MODULES:
        module(state, "мне важно, чтобы всем было спокойно, поэтому я всё контролирую, а потом расслабляюсь")

    assert [a for a in Axis if axis_is_closed(a, state.evidence)] == []


# --- накопление ---

def test_two_confirmations_from_different_sources_close_the_axis():
    state = _evidence(
        _sig("J", "планирует день заранее", source="llm"),
        _sig("J", "настойчивость и контроль процесса", source="module", confidence=0.3),
    )
    assert axis_is_closed(Axis.JP, state.evidence)


def test_score_exactly_on_the_threshold_closes_the_axis():
    """
    Регресс на арифметику: 0.6 + 0.3 в float даёт 0.8999999999999999,
    и ось не закрывалась ровно на пороговом наборе сигналов.
    """
    state = _evidence(
        _sig("J", "первое наблюдение", source="llm", confidence=0.6),
        _sig("J", "второе наблюдение", source="module", confidence=0.3),
    )
    assert weigh_axis(Axis.JP, state.evidence).score == 0.9
    assert axis_is_closed(Axis.JP, state.evidence)


def test_single_source_without_episode_is_not_enough():
    """Два наблюдения от одной только LLM без конкретного эпизода — ещё не закрытие."""
    state = _evidence(
        _sig("J", "планирует день заранее"),
        _sig("J", "не любит менять планы"),
    )
    assert not axis_is_closed(Axis.JP, state.evidence)


def test_single_source_with_real_episode_is_enough():
    state = _evidence(
        _sig("J", "планирует день заранее"),
        _sig("J", "вчера довела релиз до конца сама", direct=True),
    )
    assert axis_is_closed(Axis.JP, state.evidence)


def test_contradiction_is_not_a_closed_axis():
    """Разнонаправленные сигналы — это пограничный профиль, а не закрытая ось."""
    state = _evidence(
        _sig("J", "планирует заранее", direct=True),
        _sig("P", "легко меняет планы на ходу", direct=True),
    )
    assert not axis_is_closed(Axis.JP, state.evidence)
    assert not soft_axis_closed(Axis.JP, state.evidence)


def test_weight_reports_leading_direction_and_opposition():
    state = _evidence(
        _sig("J", "планирует заранее"),
        _sig("J", "держит структуру за других"),
        _sig("P", "иногда бросает начатое", confidence=0.3),
    )
    w = weigh_axis(Axis.JP, state.evidence)

    assert w.direction == "J"
    assert w.score == pytest.approx(1.2)
    assert w.opposing == pytest.approx(0.3)
    assert w.signals == 2


# --- инвариант ---

@pytest.mark.parametrize("signals", [
    [_sig("J", "a"), _sig("J", "b", source="module", confidence=0.3)],
    [_sig("J", "a"), _sig("J", "b", direct=True)],
    [_sig("J", "a")],
    [_sig("J", "a"), _sig("P", "b")],
    [_sig("J", "a", confidence=0.25, source="module"), _sig("J", "b", confidence=0.25, source="energy")],
])
def test_hard_closed_always_implies_soft_closed(signals):
    """
    Раньше было наоборот: soft требовал два сигнала, а hard довольствовался одним
    с direct_example — «мягкое» условие оказывалось строже «жёсткого».
    """
    state = _evidence(*signals)

    if axis_is_closed(Axis.JP, state.evidence):
        assert soft_axis_closed(Axis.JP, state.evidence)


def test_empty_axis_is_closed_by_nothing():
    state = ConversationState()
    assert not axis_is_closed(Axis.JP, state.evidence)
    assert not soft_axis_closed(Axis.JP, state.evidence)
    assert weigh_axis(Axis.JP, state.evidence).direction is None


# --- дубли ---

def test_repeated_signal_does_not_inflate_the_axis():
    """LLM переотправляет уже собранное наблюдение дословно — вес расти не должен."""
    state = ConversationState()
    for _ in range(3):
        state.add_signals([_sig("J", "планирует день заранее", direct=True)])

    assert len(state.evidence.signals) == 1
    assert not axis_is_closed(Axis.JP, state.evidence)


def test_different_observations_are_kept():
    state = _evidence(
        _sig("J", "планирует день заранее"),
        _sig("J", "держит структуру за других"),
    )
    assert len(state.evidence.signals) == 2
