from core.models import ConversationState
from modules.compensation_patterns import compensation_patterns_module


def test_compensation_detected():
    s = ConversationState()

    r = compensation_patterns_module(
        s,
        "Мне приходится постоянно всё контролировать, "
        "иначе без меня команда разваливается, и это очень выматывает."
    )

    assert r.activated is True
    assert "compensation_pattern_detected" in s.flags
    assert r.vl_delta == 0


def test_compensation_with_awareness():
    s = ConversationState()

    r = compensation_patterns_module(
        s,
        "Я понимаю, что постоянно контролирую процессы не потому что люблю это, "
        "а потому что иначе всё ломается, и это не совсем моё."
    )

    assert r.activated is True
    assert r.vl_delta == 1
