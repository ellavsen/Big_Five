"""Кнопка «Открыть карту» в боте.

Адрес Mini App зависит от того, где поднят веб-сервис, поэтому приходит
из окружения. Без него кнопки нет: бот полностью работоспособен и без неё,
а вести человека на несуществующую страницу хуже, чем не звать вовсе.
"""
import pytest

from app.telegram_bot import webapp_keyboard


def test_no_url_no_button(monkeypatch):
    monkeypatch.delenv("WEBAPP_URL", raising=False)
    assert webapp_keyboard() is None


def test_empty_url_no_button(monkeypatch):
    monkeypatch.setenv("WEBAPP_URL", "   ")
    assert webapp_keyboard() is None


@pytest.mark.parametrize("url", [
    "http://example.com",          # Telegram открывает только https
    "localhost:8000",
    "example.com",
])
def test_non_https_is_refused(monkeypatch, url):
    monkeypatch.setenv("WEBAPP_URL", url)
    assert webapp_keyboard() is None, "Telegram не откроет такой адрес — кнопка обманет"


def test_https_url_gives_a_web_app_button(monkeypatch):
    monkeypatch.setenv("WEBAPP_URL", "https://example.trycloudflare.com")

    button = webapp_keyboard().inline_keyboard[0][0]

    assert button.web_app is not None, "должна открывать Mini App, а не просто ссылку"
    assert button.web_app.url == "https://example.trycloudflare.com"
    assert "карт" in button.text.lower()


# --- /akme после перезапуска бота -----------------------------------------

import pytest as _pytest  # noqa: E402

import app.telegram_bot as bot  # noqa: E402
from core.models import ConversationState  # noqa: E402


class _Msg:
    def __init__(self):
        self.replies: list[str] = []

    async def reply_text(self, text, reply_markup=None, parse_mode=None):
        self.replies.append(text)


class _User:
    id = 4242
    username = "tester"


class _Update:
    def __init__(self):
        self.message = _Msg()
        self.effective_user = _User()


class _FakeSession:
    """Подменяет сессию к базе: до неё дело всё равно не доходит, Repo подменён.

    Без этой подмены тест звал настоящий get_sessionmaker(), и локально это
    проходило только потому, что DATABASE_URL подтягивался из .env. На CI
    переменной нет — и тест падал. Ровно то, ради чего CI и нужен.
    """

    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


def _fake_sessionmaker():
    return _FakeSession


PROFILE = {
    "message": "итог",
    "trait_scores": {"openness": 0.5, "conscientiousness": 0.73,
                     "extraversion": 0.5, "agreeableness": 0.5, "neuroticism": 0.66},
    "core_vs_role": {"core": [], "role": []},
    "notes": [],
    "akme_vector": {"core": [], "unload": [], "environment": [], "risk": []},
}


@_pytest.mark.asyncio
async def test_akme_falls_back_to_the_stored_profile(monkeypatch):
    """После перезапуска бота горячее состояние пустое, а профиль в базе есть.

    Живой случай: человек нажал «Практические рекомендации» и услышал «пока рано»,
    хотя три его итога лежали в базе. Снимок завершённой сессии затирается
    намеренно — значит /akme обязан уметь брать профиль из таблицы.
    """
    from datetime import datetime, timezone

    async def _empty_state(user_id):
        return ConversationState(telegram_id=user_id)

    async def _noop(*a, **kw):
        return None

    class _Repo:
        def __init__(self, db):
            pass

        async def get_last_profile(self, tg_id):
            return datetime(2026, 7, 26, tzinfo=timezone.utc), PROFILE

    monkeypatch.setattr(bot, "_get_state", _empty_state)
    monkeypatch.setattr(bot, "_ensure_db_session_for_user", _noop)
    monkeypatch.setattr(bot, "Repo", _Repo)
    monkeypatch.setattr(bot, "get_sessionmaker", _fake_sessionmaker)
    monkeypatch.delenv("WEBAPP_URL", raising=False)

    update = _Update()
    await bot.akme_cmd(update, None)

    answer = update.message.replies[0]
    assert "Пока рано" not in answer
    assert "прошлого разговора" in answer, "человек должен понимать, что итог не сегодняшний"
    assert "Практические рекомендации" in answer


@_pytest.mark.asyncio
async def test_akme_still_says_when_there_is_nothing(monkeypatch):
    async def _empty_state(user_id):
        return ConversationState(telegram_id=user_id)

    async def _noop(*a, **kw):
        return None

    class _Repo:
        def __init__(self, db):
            pass

        async def get_last_profile(self, tg_id):
            return None

    monkeypatch.setattr(bot, "_get_state", _empty_state)
    monkeypatch.setattr(bot, "_ensure_db_session_for_user", _noop)
    monkeypatch.setattr(bot, "Repo", _Repo)
    monkeypatch.setattr(bot, "get_sessionmaker", _fake_sessionmaker)

    update = _Update()
    await bot.akme_cmd(update, None)

    assert "Пока рано" in update.message.replies[0]
