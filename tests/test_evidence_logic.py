from core.evidence_logic import axis_is_closed
from core.models import Axis, AxisSignal

def test_axis_closed_by_direct_example():
    signals = [
        AxisSignal(axis=Axis.EI, direction="I", source="direct_example", text="В команде устаю", context="team")
    ]
    assert axis_is_closed(signals) is True

def test_axis_closed_by_two_sources():
    signals = [
        AxisSignal(axis=Axis.EI, direction="I", source="energy", text="созвоны выматывают", context="work"),
        AxisSignal(axis=Axis.EI, direction="I", source="team", text="в группе быстро устаю", context="team"),
    ]
    assert axis_is_closed(signals) is True

def test_axis_not_closed_by_one_non_example():
    signals = [
        AxisSignal(axis=Axis.EI, direction="I", source="energy", text="созвоны выматывают", context="work")
    ]
    assert axis_is_closed(signals) is False
