from core.models import ConversationState
from modules.role_vs_core import role_vs_core_module
from modules.energy_economy import energy_economy_module
from core.models import Axis


def test_role_vs_core_sets_flag():
    s = ConversationState()
    r = role_vs_core_module(s, "По работе приходится быть очень общительной, так надо.")
    assert r.activated is True
    assert "role_core_tension" in s.flags

def test_energy_module_adds_signals():
    s = ConversationState()
    r = energy_economy_module(
        s,
        "Созвоны и встречи выматывают, потом хочется выдохнуть."
    )

    assert r.activated is True

    ei_signals = s.evidence.signals_for(Axis.EI)
    assert len(ei_signals) >= 1

    assert ei_signals[0].source == "energy"
    assert ei_signals[0].direction in {"I", "E"}