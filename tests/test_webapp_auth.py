"""Проверка подписи initData.

Самое опасное место проекта: отсюда решается, чей профиль отдать. Поэтому
тестов здесь больше, чем «работает на правильных данных» — важнее, что не
работает на неправильных.

Всё считается локально: ни Telegram, ни сети, ни хостинга не нужно.
"""
import json
import time
from urllib.parse import urlencode

import pytest

from app.webapp_auth import InitDataError, WebAppUser, sign_init_data, verify_init_data

TOKEN = "123456:AAEtestTokenNotReal"
OTHER_TOKEN = "654321:AAEsomeOtherBotToken"
MAX_AGE = 3600


def make_init_data(
    telegram_id: int = 777,
    username: str | None = "tester",
    auth_date: int | None = None,
    token: str = TOKEN,
    **extra: str,
) -> str:
    """Собирает initData ровно так, как её собрал бы Telegram."""
    user = {"id": telegram_id, "first_name": "Тест"}
    if username:
        user["username"] = username

    pairs = {
        "user": json.dumps(user, ensure_ascii=False, separators=(",", ":")),
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAHtest",
        **extra,
    }
    pairs["hash"] = sign_init_data({k: v for k, v in pairs.items()}, token)
    return urlencode(pairs)


def test_valid_init_data_gives_the_user():
    user = verify_init_data(make_init_data(), TOKEN, MAX_AGE)
    assert user == WebAppUser(telegram_id=777, username="tester")


def test_user_without_username_is_fine():
    user = verify_init_data(make_init_data(username=None), TOKEN, MAX_AGE)
    assert user.telegram_id == 777
    assert user.username is None


def test_substituted_user_id_is_rejected():
    """Главный тест этапа: подменить id, сохранив чужую подпись, нельзя.

    Ровно так выглядела бы попытка прочитать чужой психологический профиль.
    """
    init_data = make_init_data(telegram_id=777)
    tampered = init_data.replace("777", "888")
    assert tampered != init_data

    with pytest.raises(InitDataError):
        verify_init_data(tampered, TOKEN, MAX_AGE)


def test_forged_hash_is_rejected():
    init_data = make_init_data()
    forged = init_data.rsplit("hash=", 1)[0] + "hash=" + "0" * 64

    with pytest.raises(InitDataError):
        verify_init_data(forged, TOKEN, MAX_AGE)


def test_signature_from_another_bot_is_rejected():
    """Подпись чужого бота не годится: секрет выводится из токена."""
    init_data = make_init_data(token=OTHER_TOKEN)

    with pytest.raises(InitDataError):
        verify_init_data(init_data, TOKEN, MAX_AGE)


def test_expired_init_data_is_rejected():
    """Подпись верна вечно — окно ограничивает только возраст."""
    old = make_init_data(auth_date=int(time.time()) - MAX_AGE - 60)

    with pytest.raises(InitDataError):
        verify_init_data(old, TOKEN, MAX_AGE)


def test_fresh_init_data_within_window_passes():
    recent = make_init_data(auth_date=int(time.time()) - MAX_AGE + 60)
    assert verify_init_data(recent, TOKEN, MAX_AGE).telegram_id == 777


def test_extra_field_is_covered_by_signature():
    """Подпись покрывает все поля, а не только известные нам."""
    init_data = make_init_data(start_param="promo")
    assert verify_init_data(init_data, TOKEN, MAX_AGE).telegram_id == 777

    tampered = init_data.replace("promo", "hacked")
    with pytest.raises(InitDataError):
        verify_init_data(tampered, TOKEN, MAX_AGE)


@pytest.mark.parametrize(
    "init_data",
    [
        pytest.param("", id="пусто"),
        pytest.param("user=%7B%22id%22%3A777%7D&auth_date=1", id="без hash"),
        pytest.param("не=пары&и=вообще=мусор", id="битая строка"),
    ],
)
def test_malformed_init_data_is_rejected(init_data):
    with pytest.raises(InitDataError):
        verify_init_data(init_data, TOKEN, MAX_AGE)


def test_without_bot_token_nothing_is_trusted():
    """Пустой токен — не повод пропустить: проверить подпись нечем."""
    with pytest.raises(InitDataError):
        verify_init_data(make_init_data(), "", MAX_AGE)


def test_auth_date_is_checked_after_signature():
    """Мусор в auth_date не должен ронять проверку раньше подписи."""
    init_data = make_init_data(auth_date=0).replace("auth_date=0", "auth_date=завтра")

    with pytest.raises(InitDataError):
        verify_init_data(init_data, TOKEN, MAX_AGE)
