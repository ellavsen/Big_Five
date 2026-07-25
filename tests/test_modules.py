from core.models import ConversationState, Direction, Trait
from modules.compensation_patterns import compensation_patterns
from modules.energy_economy import energy_economy
from modules.role_vs_core import role_vs_core


def test_negated_control_gives_no_signal():
    """«не контролирую» ≠ контроль. До 2C давало точно такой же сигнал."""
    s = ConversationState()

    compensation_patterns(s, "я вообще ничего не контролирую, всё пускаю на самотёк")

    assert s.notes == []
    assert s.evidence.signals == []


def test_direct_example_only_on_a_concrete_episode():
    """Самоописание — это не наблюдаемый случай, и прямым примером считаться не должно."""
    habit = ConversationState()
    compensation_patterns(habit, "я всё время всё контролирую")

    episode = ConversationState()
    compensation_patterns(episode, "вчера я контролировала каждый шаг команды")

    assert habit.evidence.signals_for(Trait.CONSCIENTIOUSNESS)[0].direct_example is False
    assert episode.evidence.signals_for(Trait.CONSCIENTIOUSNESS)[0].direct_example is True


def test_control_reads_as_conscientiousness():
    s = ConversationState()

    compensation_patterns(s, "мне приходится постоянно всё контролировать")

    signal = s.evidence.signals_for(Trait.CONSCIENTIOUSNESS)[0]
    assert signal.direction is Direction.HIGH
    assert "compensation:control" in s.notes


def test_role_vs_core_marks_role_without_core():
    s = ConversationState()

    role_vs_core(s, "По работе приходится быть очень общительной, так надо.")

    assert "role_dominant" in s.notes


def test_core_expression_reads_as_agreeableness():
    s = ConversationState()

    role_vs_core(s, "Мне важно, чтобы людям было спокойно рядом.")

    assert "core_expression" in s.notes
    assert [sig.direction for sig in s.evidence.signals_for(Trait.AGREEABLENESS)] == [Direction.HIGH]


# --- то, ради чего заводилась пятая черта ---

def test_depletion_reads_as_high_neuroticism():
    """
    Раньше истощение вообще не давало сигнала: в четырёх осях MBTI
    для реактивности на стресс не было места.
    """
    s = ConversationState()

    energy_economy(s, "Созвоны выматывают, после них нет сил.")

    assert "energy:depletion" in s.notes
    signal = s.evidence.signals_for(Trait.NEUROTICISM)[0]
    assert signal.direction is Direction.HIGH
    assert signal.source == "energy"


def test_recovery_reads_as_low_neuroticism_not_sensing():
    """
    Регресс: восстановление уезжало в сигнал Sensing (SN → S), потому что
    положить его было больше некуда. Телесное облегчение — это не сенсорика.
    """
    s = ConversationState()

    energy_economy(s, "после прогулки я расслабляюсь и становится легче")

    assert "energy:recovery" in s.notes
    signal = s.evidence.signals_for(Trait.NEUROTICISM)[0]
    assert signal.direction is Direction.LOW
    assert signal.source == "energy"
    assert s.evidence.signals_for(Trait.OPENNESS) == []


def test_energy_economy_ignores_neutral_text():
    s = ConversationState()

    energy_economy(s, "Вчера был обычный рабочий день.")

    assert s.notes == []
    assert s.evidence.signals == []
