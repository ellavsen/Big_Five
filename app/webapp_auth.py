"""Проверка подлинности `initData` из Telegram Mini App.

Это единственное, что отделяет чужой психологический профиль от публичного
доступа. Telegram отдаёт странице строку с данными о том, кто её открыл, и
подписывает её HMAC-SHA256 на секрете, выведенном из токена бота. Подделать
подпись, не зная токена, нельзя — а значит `user_id` внутри можно верить.

Без этой проверки достаточно подставить в запрос чужой `user_id`, чтобы
прочитать чужой профиль. Профиль — спецкатегория ПДн, так что цена ошибки
здесь выше, чем во всём остальном проекте.

Алгоритм задан Telegram и менять его нельзя:
  secret = HMAC_SHA256(key="WebAppData", msg=<токен бота>)
  hash   = HMAC_SHA256(key=secret, msg=<пары ключ=значение, отсортированные, через \n>)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class InitDataError(Exception):
    """initData не прошла проверку.

    Текст — для лога. Наружу отдаётся один и тот же ответ на любую причину:
    подробности того, что именно не сошлось, помогают только подбирающему.
    """


@dataclass(frozen=True)
class WebAppUser:
    telegram_id: int
    username: str | None


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def _data_check_string(pairs: dict[str, str]) -> str:
    return "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))


def sign_init_data(pairs: dict[str, str], bot_token: str) -> str:
    """Считает подпись для набора полей.

    Нужна и в проверке, и в тестах: собрать правдоподобную initData можно только
    тем же алгоритмом, которым её подписывает Telegram.
    """
    return hmac.new(
        _secret_key(bot_token),
        _data_check_string(pairs).encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_init_data(init_data: str, bot_token: str, max_age_seconds: int) -> WebAppUser:
    """Проверяет подпись и возраст initData и достаёт из неё пользователя.

    Порядок важен: сначала подпись, потом всё остальное. До проверки подписи
    ни одному полю внутри верить нельзя, включая `auth_date`.
    """
    if not init_data:
        raise InitDataError("пустая initData")
    if not bot_token:
        raise InitDataError("не задан токен бота — проверить подпись нечем")

    # strict_parsing: битую строку честнее отвергнуть целиком, чем разобрать
    # наполовину и проверить подпись по огрызку.
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True, keep_blank_values=True))
    except ValueError as exc:
        raise InitDataError("initData не разбирается") from exc

    received_hash = pairs.pop("hash", "")
    if not received_hash:
        raise InitDataError("в initData нет hash")

    expected_hash = sign_init_data(pairs, bot_token)

    # compare_digest, а не `==`: обычное сравнение строк выходит из цикла на
    # первом несовпавшем байте, и по времени ответа подпись подбирается побайтно.
    if not hmac.compare_digest(expected_hash, received_hash):
        raise InitDataError("подпись не совпала")

    # Дальше — данные, чья подлинность уже доказана.
    try:
        auth_date = int(pairs["auth_date"])
    except (KeyError, ValueError) as exc:
        raise InitDataError("в initData нет корректного auth_date") from exc

    # Подпись бессрочна: единожды подсмотренную initData иначе можно было бы
    # предъявлять сколько угодно. Возраст ограничивает это окно.
    if time.time() - auth_date > max_age_seconds:
        raise InitDataError("initData просрочена")

    try:
        user = json.loads(pairs["user"])
        telegram_id = int(user["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InitDataError("в initData нет пользователя") from exc

    username = user.get("username")
    return WebAppUser(
        telegram_id=telegram_id,
        username=username if isinstance(username, str) else None,
    )
