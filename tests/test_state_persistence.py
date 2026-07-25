import json
import uuid

import pytest

import app.telegram_bot as bot
from core.models import ConversationState, Direction, Trait, TraitSignal

SESSION_ID = uuid.UUID("6f1d3c8e-0000-4000-8000-000000000001")
USER_ID = 4242


@pytest.fixture(autouse=True)
def clean_memory():
    bot.USER_STATES.clear()
    bot._LAST_SEEN.clear()
    yield
    bot.USER_STATES.clear()
    bot._LAST_SEEN.clear()


def _mid_dialogue_state() -> ConversationState:
    """Состояние с тем, что легко потерять при сериализации."""
    s = ConversationState(session_id=str(SESSION_ID), telegram_id=USER_ID)
    s.add_user("вчера сорвался релиз, я до ночи всё переделывала сама")
    s.add_assistant("как ты восстанавливаешься?")
    s.add_signals([
        TraitSignal(trait=Trait.CONSCIENTIOUSNESS, direction=Direction.HIGH,
                    text="доделала сама", source="llm", direct_example=True),
    ])
    s.add_note("compensation:control")
    s.trait_closed[Trait.CONSCIENTIOUSNESS] = True
    s.validity_level = 7
    s.goals.sig = 6
    s.synthesis_confirmed = True
    return s


def test_state_survives_json_roundtrip():
    """
    Снимок уезжает в JSONB и возвращается. Легко ломается на Trait-ключах
    в trait_closed: JSON знает только строковые ключи.
    """
    original = _mid_dialogue_state()

    blob = json.dumps(original.model_dump(mode="json"), ensure_ascii=False)
    restored = ConversationState.model_validate(json.loads(blob))

    assert restored == original
    assert isinstance(next(iter(restored.trait_closed)), Trait)
    # 2612-правило: без этого флага пользователю пришлось бы подтверждать итог заново
    assert restored.synthesis_confirmed is True


def test_snapshot_restores_full_state():
    snapshot = _mid_dialogue_state().model_dump(mode="json")

    state = bot._state_from_snapshot(SESSION_ID, snapshot)

    assert state.session_id == str(SESSION_ID)
    assert state.validity_level == 7
    assert len(state.history) == 2
    assert state.evidence.signals[0].trait is Trait.CONSCIENTIOUSNESS


def test_empty_snapshot_reuses_session():
    """
    Процесс упал до первого хода: сессия в БД есть, снимка нет.
    Начинаем с чистого состояния, но в ту же сессию — иначе в БД копятся
    брошенные active-сессии, и rehydrate будет цепляться не за ту.
    """
    state = bot._state_from_snapshot(SESSION_ID, None)

    assert state.session_id == str(SESSION_ID)
    assert state.history == []


def test_broken_snapshot_does_not_crash_the_dialogue():
    """Контракт состояния мог поменяться между версиями — старый снимок не должен ронять бота."""
    state = bot._state_from_snapshot(SESSION_ID, {"validity_level": "не число"})

    assert state.session_id == str(SESSION_ID)
    assert state.validity_level == ConversationState().validity_level


@pytest.mark.asyncio
async def test_get_state_rehydrates_when_memory_is_empty(monkeypatch):
    restored = _mid_dialogue_state()

    async def _fake_rehydrate(user_id):
        assert user_id == USER_ID
        return restored

    monkeypatch.setattr(bot, "_rehydrate_state", _fake_rehydrate)

    state = await bot._get_state(USER_ID)

    assert state is restored
    assert bot.USER_STATES[USER_ID] is restored


@pytest.mark.asyncio
async def test_get_state_does_not_touch_db_when_state_is_hot(monkeypatch):
    async def _boom(user_id):
        raise AssertionError("горячее состояние не должно ходить в БД")

    monkeypatch.setattr(bot, "_rehydrate_state", _boom)
    hot = _mid_dialogue_state()
    bot.USER_STATES[USER_ID] = hot

    assert await bot._get_state(USER_ID) is hot


def test_stale_state_is_evicted():
    bot.USER_STATES[USER_ID] = _mid_dialogue_state()
    bot._LAST_SEEN[USER_ID] = 1000.0

    evicted = bot._evict_stale_states(now=1000.0 + bot.STATE_TTL_SECONDS + 1)

    assert evicted == [USER_ID]
    assert USER_ID not in bot.USER_STATES


def test_fresh_state_is_kept():
    bot.USER_STATES[USER_ID] = _mid_dialogue_state()
    bot._LAST_SEEN[USER_ID] = 1000.0

    assert bot._evict_stale_states(now=1000.0 + bot.STATE_TTL_SECONDS - 1) == []
    assert USER_ID in bot.USER_STATES


def test_fresh_state_is_visible_to_the_evictor():
    """
    /start и сброс кладут состояние в память напрямую. Без отметки времени уборщик
    такую запись не увидит вовсе — и она останется в памяти навсегда.
    """
    state = bot._put_fresh_state(USER_ID)
    state.session_id = str(SESSION_ID)  # как будто сессия уже создана в БД
    bot._LAST_SEEN[USER_ID] = 1000.0

    assert bot._evict_stale_states(now=1000.0 + bot.STATE_TTL_SECONDS + 1) == [USER_ID]


def test_unsaved_state_is_never_evicted():
    """
    Без session_id состояние ни разу не доехало до БД — выбросить его значит
    молча потерять разговор, потому что rehydrate его не вернёт.
    """
    bot.USER_STATES[USER_ID] = ConversationState()  # session_id ещё нет
    bot._LAST_SEEN[USER_ID] = 1000.0

    assert bot._evict_stale_states(now=1000.0 + bot.STATE_TTL_SECONDS * 100) == []
    assert USER_ID in bot.USER_STATES
