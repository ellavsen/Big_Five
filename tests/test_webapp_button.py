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
