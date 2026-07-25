"""
Регресс на кнопки бота: обе ветки ниже падали NameError в проде.
Хендлеры проверяем без сети и без Postgres — БД-вызовы подменены.
"""
import pytest

import app.telegram_bot as bot
from core.models import ConversationState
from core.orchestrator import Orchestrator
from tests.fakes import FakeLLM

USER_ID = 111


class _FakeMessage:
    def __init__(self, text: str):
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str, reply_markup=None):
        self.replies.append(text)


class _FakeUser:
    id = USER_ID
    username = "tester"


class _FakeUpdate:
    def __init__(self, text: str):
        self.message = _FakeMessage(text)
        self.effective_user = _FakeUser()


class _FakeContext:
    def __init__(self, orchestrator: Orchestrator):
        self.bot_data = {"orchestrator": orchestrator}


@pytest.fixture(autouse=True)
def clean_states():
    bot.USER_STATES.clear()
    yield
    bot.USER_STATES.clear()


@pytest.fixture
def saved(monkeypatch) -> list[dict]:
    """Подменяет запись в БД и возвращает список того, что бот пытался сохранить."""
    calls: list[dict] = []

    async def _save(state, role: str, text: str, source: str = "text"):
        calls.append({"role": role, "text": text, "source": source})

    async def _noop(*args, **kwargs):
        return None

    async def _consented(tg_id: int) -> bool:
        return True

    monkeypatch.setattr(bot, "_save_message_to_db", _save)
    monkeypatch.setattr(bot, "_ensure_db_session_for_user", _noop)
    monkeypatch.setattr(bot, "_persist_step_state", _noop)
    monkeypatch.setattr(bot, "_persist_synthesis_and_finish", _noop)
    # эти тесты про кнопки, а не про согласие — считаем, что оно уже дано
    monkeypatch.setattr(bot, "_has_consent", _consented)
    return calls


@pytest.fixture
def context() -> _FakeContext:
    return _FakeContext(
        Orchestrator(llm=FakeLLM("Расскажи подробнее?"), turn_planner_prompt="T", synthesizer_prompt="S")
    )


@pytest.mark.asyncio
async def test_show_transcript_button(saved, context):
    """Раньше: NameError: fixed_text — переменной в этой ветке не существует."""
    bot.USER_STATES[USER_ID] = ConversationState(last_transcript="я вчера очень устала")
    update = _FakeUpdate("📝 Показать распознанный текст")

    await bot.handle_message(update, context)

    state = bot.USER_STATES[USER_ID]
    assert state.awaiting_transcript_fix is True
    assert "я вчера очень устала" in update.message.replies[0]
    # показ транскрипта сам по себе ничего не сохраняет
    assert saved == []


@pytest.mark.asyncio
async def test_show_transcript_button_without_transcript(saved, context):
    bot.USER_STATES[USER_ID] = ConversationState()
    update = _FakeUpdate("📝 Показать распознанный текст")

    await bot.handle_message(update, context)

    assert bot.USER_STATES[USER_ID].awaiting_transcript_fix is False
    assert "Пока нет распознанного текста" in update.message.replies[0]


@pytest.mark.asyncio
async def test_continue_conversation_button(saved, context):
    """Раньше: NameError: response — ответа оркестратора в этой ветке нет."""
    bot.USER_STATES[USER_ID] = ConversationState(synthesis_confirmed=True)
    update = _FakeUpdate("↩️ Продолжим разговор")

    await bot.handle_message(update, context)

    assert bot.USER_STATES[USER_ID].synthesis_confirmed is False
    assert update.message.replies == ["Хорошо, продолжаем 🙂"]
    assert saved == [{"role": "assistant", "text": "Хорошо, продолжаем 🙂", "source": "system"}]


@pytest.mark.asyncio
async def test_transcript_fix_is_saved_and_goes_to_orchestrator(saved, context):
    """Исправленный текст должен попадать и в state, и в БД как transcript_fix."""
    bot.USER_STATES[USER_ID] = ConversationState(
        last_transcript="я вчера очень усталая",
        awaiting_transcript_fix=True,
    )
    update = _FakeUpdate("я вчера очень устала")

    await bot.handle_message(update, context)

    state = bot.USER_STATES[USER_ID]
    assert state.awaiting_transcript_fix is False
    assert state.last_transcript == "я вчера очень устала"

    assert saved[0] == {
        "role": "user",
        "text": "я вчера очень устала",
        "source": "transcript_fix",
    }
    assert update.message.replies == ["Расскажи подробнее?"]
