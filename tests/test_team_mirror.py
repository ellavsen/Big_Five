from core.models import ConversationState, Direction, Trait
from modules.team_mirror import team_mirror


def test_team_mirror_adds_conscientiousness_on_repeating_role():
    s = ConversationState()

    team_mirror(s, "В команде я обычно разруливаю конфликты и я закрываю задачи за других.")

    signals = s.evidence.signals_for(Trait.CONSCIENTIOUSNESS)
    assert len(signals) == 1
    assert signals[0].direction is Direction.HIGH
    assert signals[0].source == "module"
    # эпизодических маркеров в тексте нет — значит это не прямой пример
    assert signals[0].direct_example is False


def test_team_mirror_marks_direct_example_on_concrete_episode():
    s = ConversationState()

    team_mirror(s, "Вчера я разруливаю ситуацию с дедлайном и поддерживаю коллег.")

    assert s.evidence.signals_for(Trait.CONSCIENTIOUSNESS)[0].direct_example is True
    # явная поддержка/гармонизация добавляет отдельное наблюдение по доброжелательности
    assert [sig.direction for sig in s.evidence.signals_for(Trait.AGREEABLENESS)] == [Direction.HIGH]


def test_team_mirror_ignores_text_without_role_markers():
    s = ConversationState()

    team_mirror(s, "Вчера был спокойный день, гуляли в парке.")

    assert s.notes == []
    assert s.evidence.signals == []
