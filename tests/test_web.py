"""Эндпоинт Mini App: кому отдаётся профиль и что именно уходит наружу.

База сюда не поднимается — загрузка профиля подменяется. Проверяется решение
«чей профиль отдать», а не SQL: он уже покрыт в другом месте.
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import app.web as web
from tests.test_webapp_auth import TOKEN, make_init_data

FINISHED_AT = datetime(2026, 7, 20, 12, 30, tzinfo=timezone.utc)

RAW_PROFILE = {
    "message": "Первый абзац итога.\n\nВторой абзац итога.",
    "trait_scores": {
        "openness": 0.47,
        "conscientiousness": 0.81,
        "extraversion": 0.27,
        "agreeableness": 0.66,
        "neuroticism": 0.72,
    },
    "traits_confidence": {
        "conscientiousness": {"confidence": 0.8, "stability": "устойчивая"},
    },
    "core_vs_role": {"core": ["внимательность"], "role": ["контроль в проекте"]},
    "notes": ["устал к концу недели"],
    "akme_vector": {"core": ["внимание к деталям"], "unload": [], "environment": [], "risk": []},
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    return TestClient(web.app)


@pytest.fixture
def loaded(monkeypatch):
    """Подменяет загрузку профиля и запоминает, чей профиль запрашивали."""
    asked: list[int] = []

    async def _load(telegram_id: int):
        asked.append(telegram_id)
        return (FINISHED_AT, RAW_PROFILE) if telegram_id == 777 else None

    monkeypatch.setattr(web, "_load_profile", _load)
    return asked


def test_without_init_data_no_profile(client, loaded):
    r = client.get("/api/profile")
    assert r.status_code == 401
    assert loaded == [], "до подтверждения личности в базу ходить незачем"


def test_forged_init_data_is_refused(client, loaded):
    forged = make_init_data(telegram_id=777).rsplit("hash=", 1)[0] + "hash=" + "0" * 64

    r = client.get("/api/profile", headers={"X-Telegram-Init-Data": forged})
    assert r.status_code == 401
    assert loaded == []


def test_substituted_user_id_is_refused(client, loaded):
    """Подменить id в подписанной строке и получить чужой профиль нельзя."""
    tampered = make_init_data(telegram_id=555).replace("555", "777")

    r = client.get("/api/profile", headers={"X-Telegram-Init-Data": tampered})
    assert r.status_code == 401
    assert loaded == []


def test_profile_is_loaded_for_the_signed_user(client, loaded):
    r = client.get("/api/profile", headers={"X-Telegram-Init-Data": make_init_data(telegram_id=777)})

    assert r.status_code == 200
    assert loaded == [777], "запрошен должен быть профиль того, кто подписан"


def test_missing_profile_is_not_an_error(client, loaded):
    r = client.get("/api/profile", headers={"X-Telegram-Init-Data": make_init_data(telegram_id=123)})

    assert r.status_code == 404
    assert "разговор" in r.json()["detail"]


def test_response_carries_what_the_page_needs(client, loaded):
    r = client.get("/api/profile", headers={"X-Telegram-Init-Data": make_init_data(telegram_id=777)})
    body = r.json()

    assert body["finished_at"].startswith("2026-07-20")
    assert len(body["traits"]) == 5
    assert body["message"] == ["Первый абзац итога.", "Второй абзац итога."]
    assert body["core_vs_role"]["role"] == ["контроль в проекте"]

    # четыре буквы считаются из черт: открытость 0.47 между порогами → X
    assert body["mbti"]["letters"] == "IXFJ"
    assert body["mbti"]["is_complete"] is False
    assert body["mbti"]["disclaimer"]

    # блоки энергии собирает тот же модуль, что и /akme в боте
    assert "внимание к деталям" in body["akme"]["core"]
    assert body["akme"]["risk"], "риски должны считаться, а не приходить пустыми"


def test_missing_trait_confidence_does_not_break_the_page(client, loaded):
    """У профиля старого формата уверенности может не быть вовсе."""
    r = client.get("/api/profile", headers={"X-Telegram-Init-Data": make_init_data(telegram_id=777)})

    by_key = {t["key"]: t for t in r.json()["traits"]}
    assert by_key["conscientiousness"]["confidence"] == 0.8
    assert by_key["openness"]["confidence"] == 0.0
    assert by_key["openness"]["stability"] == "пограничная"


def test_raw_conversation_never_leaves_the_server(client, loaded):
    """Наружу уходит только производное от синтеза, не сам разговор."""
    r = client.get("/api/profile", headers={"X-Telegram-Init-Data": make_init_data(telegram_id=777)})
    body = r.json()

    assert "notes" not in body
    assert "probabilities" not in body
    assert "устал к концу недели" not in r.text, "заметки — сырой материал, наружу им не надо"
