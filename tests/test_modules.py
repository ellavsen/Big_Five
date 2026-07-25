from core.models import Axis, ConversationState
from modules.compensation_patterns import compensation_patterns
from modules.energy_economy import energy_economy
from modules.role_vs_core import role_vs_core


def test_negated_control_gives_no_signal():
    """«не контролирую» ≠ контроль. До 2C давало точно такой же сигнал J."""
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

    assert habit.evidence.signals_for(Axis.JP)[0].direct_example is False
    assert episode.evidence.signals_for(Axis.JP)[0].direct_example is True


def test_energy_signal_is_marked_as_energy_source():
    """
    source="module" вместо "energy" делал ветку confidence="high"
    в modules/synthesizer.py недостижимой.
    """
    s = ConversationState()

    energy_economy(s, "после прогулки я расслабляюсь и становится легче")

    assert s.evidence.signals_for(Axis.SN)[0].source == "energy"


def test_role_vs_core_marks_role_without_core():
    s = ConversationState()

    role_vs_core(s, "По работе приходится быть очень общительной, так надо.")

    assert "role_dominant" in s.notes


def test_role_vs_core_adds_tf_signal_on_core_expression():
    s = ConversationState()

    role_vs_core(s, "Мне важно, чтобы людям было спокойно рядом.")

    assert "core_expression" in s.notes
    assert [sig.direction for sig in s.evidence.signals_for(Axis.TF)] == ["F"]


def test_energy_economy_notes_depletion():
    s = ConversationState()

    energy_economy(s, "Созвоны выматывают, после них нет сил.")

    assert "energy:depletion" in s.notes


def test_energy_economy_ignores_neutral_text():
    s = ConversationState()

    energy_economy(s, "Вчера был обычный рабочий день.")

    assert s.notes == []
    assert s.evidence.signals == []
