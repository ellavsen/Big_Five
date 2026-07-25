from core.matching import find_marker, has_episode

CONTROL = ["контрол", "до конца"]


def test_marker_is_found_without_negation():
    assert find_marker("я всё контролирую сама", CONTROL) == "контрол"


def test_negation_before_marker_blocks_it():
    """Главный баг 2C: «не контролирую» давало ровно тот же сигнал, что «контролирую»."""
    assert find_marker("я ничего не контролирую", CONTROL) is None


def test_negation_further_than_window_does_not_block():
    """«не» слишком далеко и относится к другому куску фразы."""
    text = "не помню когда это началось, но теперь я контролирую каждый шаг"
    assert find_marker(text, CONTROL) == "контрол"


def test_second_clean_occurrence_still_counts():
    """Первое вхождение под отрицанием, второе — нет. Сигнал должен быть."""
    assert find_marker("не контролирую мелочи, но контролирую сроки", CONTROL) == "контрол"


def test_negation_words_are_matched_whole():
    """«не» не должно срабатывать внутри других слов — иначе матчер онемеет."""
    assert find_marker("невозможно перестать, я контролирую всё", CONTROL) == "контрол"


def test_no_marker_returns_none():
    assert find_marker("вчера гуляли в парке", CONTROL) is None


def test_episode_is_detected():
    assert has_episode("вчера я всё переделала сама") is True


def test_general_self_description_is_not_an_episode():
    assert has_episode("я обычно всё переделываю сама") is False
