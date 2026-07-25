from core.models import Axis, ConversationState
from modules.team_mirror import team_mirror


def test_team_mirror_adds_jp_signal_on_repeating_role():
    s = ConversationState()

    team_mirror(s, "В команде я обычно разруливаю конфликты и я закрываю задачи за других.")

    jp = s.evidence.signals_for(Axis.JP)
    assert len(jp) == 1
    assert jp[0].direction == "J"
    assert jp[0].source == "module"
    # эпизодических маркеров в тексте нет — значит это не прямой пример
    assert jp[0].direct_example is False


def test_team_mirror_marks_direct_example_on_concrete_episode():
    s = ConversationState()

    team_mirror(s, "Вчера я разруливаю ситуацию с дедлайном и поддерживаю коллег.")

    jp = s.evidence.signals_for(Axis.JP)
    assert jp[0].direct_example is True
    # явная поддержка/гармонизация добавляет отдельный сигнал по TF
    assert [sig.direction for sig in s.evidence.signals_for(Axis.TF)] == ["F"]


def test_team_mirror_ignores_text_without_role_markers():
    s = ConversationState()

    team_mirror(s, "Вчера был спокойный день, гуляли в парке.")

    assert s.notes == []
    assert s.evidence.signals == []
