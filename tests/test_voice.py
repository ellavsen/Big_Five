"""
Голосовая ветка. До Этапа 3.5 она не была покрыта ничем: ни тестов,
ни прогонов — при том что это второй способ вообще говорить с ботом.
"""
import pytest

import app.telegram_bot as bot
from core.orchestrator import Orchestrator
from tests.fakes import FakeLLM

USER_ID = 555


class _FakeVoice:
    file_id = "voice-1"


class _FakeMessage:
    def __init__(self, voice=None, text=""):
        self.text = text
        self.voice = voice
        self.audio = None
        self.replies: list[str] = []

    async def reply_text(self, text, reply_markup=None, parse_mode=None):
        self.replies.append(text)


class _FakeUser:
    id = USER_ID
    username = "voice_tester"


class _FakeUpdate:
    def __init__(self, voice=None, text=""):
        self.message = _FakeMessage(voice, text)
        self.effective_user = _FakeUser()


class _FakeTgFile:
    async def download_to_drive(self, path):
        with open(path, "wb") as f:
            f.write(b"fake-audio")


class _FakeBot:
    async def get_file(self, file_id):
        return _FakeTgFile()


class _FakeSTT:
    def __init__(self, text="вчера сорвался релиз, я всё переделывала сама"):
        self.text = text
        self.calls = 0

    async def transcribe(self, path):
        self.calls += 1
        return self.text


class _FakeContext:
    def __init__(self, stt=None):
        self.bot = _FakeBot()
        self.bot_data = {
            "orchestrator": Orchestrator(FakeLLM("Как ты восстанавливаешься?"), "TURN", "SYNTH"),
            "stt": stt or _FakeSTT(),
        }


@pytest.fixture(autouse=True)
def clean_states():
    bot.USER_STATES.clear()
    bot._LAST_SEEN.clear()
    yield
    bot.USER_STATES.clear()
    bot._LAST_SEEN.clear()


@pytest.fixture
def saved(monkeypatch):
    calls: list[dict] = []

    async def _save(state, role, text, source="text"):
        calls.append({"role": role, "text": text, "source": source})

    async def _noop(*a, **kw):
        return None

    async def _consented(tg_id):
        return True

    async def _no_stored_state(user_id):
        return None

    monkeypatch.setattr(bot, "_save_message_to_db", _save)
    monkeypatch.setattr(bot, "_ensure_db_session_for_user", _noop)
    monkeypatch.setattr(bot, "_persist_step_state", _noop)
    monkeypatch.setattr(bot, "_has_consent", _consented)
    monkeypatch.setattr(bot, "_rehydrate_state", _no_stored_state)
    return calls


@pytest.mark.asyncio
async def test_voice_without_consent_collects_nothing(monkeypatch):
    """Голосом обойти согласие тоже нельзя."""
    collected = []

    async def _save(state, role, text, source="text"):
        collected.append(text)

    async def _refused(tg_id):
        return False

    monkeypatch.setattr(bot, "_save_message_to_db", _save)
    monkeypatch.setattr(bot, "_has_consent", _refused)

    stt = _FakeSTT()
    update = _FakeUpdate(voice=_FakeVoice())
    await bot.handle_audio(update, _FakeContext(stt))

    assert stt.calls == 0, "аудио не должно даже уходить в распознавание"
    assert collected == []
    assert update.message.replies


@pytest.mark.asyncio
async def test_voice_is_transcribed_and_saved_as_such(saved):
    update = _FakeUpdate(voice=_FakeVoice())
    await bot.handle_audio(update, _FakeContext())

    user_msg = [c for c in saved if c["role"] == "user"]
    assert len(user_msg) == 1
    assert user_msg[0]["source"] == "voice_transcript", (
        "источник должен отличаться от текста: транскрипт мог быть распознан неверно"
    )
    assert bot.USER_STATES[USER_ID].last_transcript == user_msg[0]["text"]


@pytest.mark.asyncio
async def test_voice_goes_through_the_same_orchestrator(saved):
    update = _FakeUpdate(voice=_FakeVoice())
    await bot.handle_audio(update, _FakeContext())

    assert "Как ты восстанавливаешься?" in update.message.replies[-1]
    assert len(bot.USER_STATES[USER_ID].history) >= 2


@pytest.mark.asyncio
async def test_unrecognised_audio_asks_to_repeat(saved):
    """Whisper иногда возвращает пустоту — это не повод гонять пустой ход через LLM."""
    update = _FakeUpdate(voice=_FakeVoice())
    await bot.handle_audio(update, _FakeContext(_FakeSTT(text="  ")))

    assert "расслышала" in update.message.replies[-1]
    assert saved == [], "ни транскрипт, ни ответ сохранять нечего"
    assert USER_ID not in bot.USER_STATES or not bot.USER_STATES[USER_ID].history


@pytest.mark.asyncio
async def test_message_without_audio_does_not_crash(saved):
    update = _FakeUpdate(voice=None)
    await bot.handle_audio(update, _FakeContext())

    assert "не получилось прочитать аудио" in update.message.replies[-1].lower()
