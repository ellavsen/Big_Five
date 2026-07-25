from core.models import Axis, ConversationState
from modules.energy_economy import energy_economy
from modules.role_vs_core import role_vs_core


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
