"""
Согласие на обработку данных. Профиль — спецкатегория ПДн, поэтому главное
здесь не «показали ли текст», а «не собрали ли что-нибудь до согласия».
"""
import pytest

import app.telegram_bot as bot
from app.consent import AGREE, DECLINE, DELETE_CANCEL, DELETE_CONFIRM
from core.config import CONSENT_VERSION
from core.orchestrator import Orchestrator
from tests.fakes import FakeLLM

USER_ID = 777


class _FakeMessage:
    def __init__(self, text: str):
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str, reply_markup=None, parse_mode=None):
        self.replies.append(text)


class _FakeUser:
    id = USER_ID
    username = "tester"


class _FakeUpdate:
    def __init__(self, text: str = ""):
        self.message = _FakeMessage(text)
        self.effective_user = _FakeUser()


class _FakeContext:
    def __init__(self):
        self.bot_data = {"orchestrator": Orchestrator(FakeLLM(), "TURN", "SYNTH")}


@pytest.fixture(autouse=True)
def clean_states():
    bot.USER_STATES.clear()
    bot._LAST_SEEN.clear()
    yield
    bot.USER_STATES.clear()
    bot._LAST_SEEN.clear()


@pytest.fixture
def spy(monkeypatch):
    """Ловит всё, что бот попытался сделать с данными пользователя."""
    calls = {"messages": [], "sessions": 0, "llm_steps": 0, "consent_written": []}

    async def _save(state, role, text, source="text"):
        calls["messages"].append(text)

    async def _ensure(state, tg_id, username):
        calls["sessions"] += 1

    async def _noop(*a, **kw):
        return None

    class _CountingOrchestrator(Orchestrator):
        async def step(self, state, user_text):
            calls["llm_steps"] += 1
            return await super().step(state, user_text)

    monkeypatch.setattr(bot, "_save_message_to_db", _save)
    monkeypatch.setattr(bot, "_ensure_db_session_for_user", _ensure)
    monkeypatch.setattr(bot, "_persist_step_state", _noop)
    monkeypatch.setattr(bot, "_persist_synthesis_and_finish", _noop)
    calls["orchestrator"] = _CountingOrchestrator(FakeLLM(), "TURN", "SYNTH")
    return calls


def _no_consent(monkeypatch):
    async def _false(tg_id):
        return False
    monkeypatch.setattr(bot, "_has_consent", _false)


def _with_consent(monkeypatch):
    async def _true(tg_id):
        return True
    monkeypatch.setattr(bot, "_has_consent", _true)


# --- главное: без согласия ничего не собирается ---

@pytest.mark.asyncio
async def test_nothing_is_collected_without_consent(spy, monkeypatch):
    _no_consent(monkeypatch)

    update = _FakeUpdate("вчера я до ночи переделывала релиз сама")
    ctx = _FakeContext()
    ctx.bot_data["orchestrator"] = spy["orchestrator"]

    await bot.handle_message(update, ctx)

    assert spy["messages"] == [], "реплика пользователя не должна попасть в БД"
    assert spy["sessions"] == 0, "сессия не должна создаваться"
    assert spy["llm_steps"] == 0, "LLM не должна вызываться"
    assert update.message.replies, "но человеку надо объяснить, почему ничего не происходит"


@pytest.mark.asyncio
async def test_start_shows_the_consent_screen_first(monkeypatch):
    _no_consent(monkeypatch)
    update = _FakeUpdate()

    await bot.start(update, _FakeContext())

    assert "психологический профиль" in update.message.replies[0]


@pytest.mark.asyncio
async def test_consent_text_states_what_is_stored_and_for_how_long(monkeypatch):
    from core.config import RETENTION_DAYS
    _no_consent(monkeypatch)
    update = _FakeUpdate()

    await bot.start(update, _FakeContext())
    text = update.message.replies[0]

    assert str(RETENTION_DAYS) in text
    assert "/delete_me" in text
    assert "не диагностика" in text


@pytest.mark.asyncio
async def test_agreement_records_the_version(spy, monkeypatch):
    written = []

    class _FakeRepo:
        def __init__(self, db):
            pass

        async def set_consent(self, tg_id, username, version):
            written.append((tg_id, version))

        async def get_active_session(self, tg_id):
            return None

    monkeypatch.setattr(bot, "Repo", _FakeRepo)
    monkeypatch.setattr(bot, "get_sessionmaker", lambda: _fake_sessionmaker())

    await bot.handle_message(_FakeUpdate(AGREE), _FakeContext())

    assert written == [(USER_ID, CONSENT_VERSION)]


def _fake_sessionmaker():
    class _Ctx:
        async def __aenter__(self):
            return None

        async def __aexit__(self, *a):
            return False

    return lambda: _Ctx()


@pytest.mark.asyncio
async def test_decline_keeps_everything_off(spy, monkeypatch):
    _no_consent(monkeypatch)
    update = _FakeUpdate(DECLINE)

    await bot.handle_message(update, _FakeContext())

    assert spy["messages"] == []
    assert spy["sessions"] == 0
    assert "не сохраняю" in update.message.replies[0]


# --- право на удаление ---

@pytest.mark.asyncio
async def test_delete_me_warns_before_deleting(monkeypatch):
    _with_consent(monkeypatch)
    update = _FakeUpdate()

    await bot.delete_me_cmd(update, _FakeContext())

    assert "Восстановить будет нельзя" in update.message.replies[0]


@pytest.mark.asyncio
async def test_delete_confirmation_wipes_the_user(monkeypatch):
    deleted = []

    class _FakeRepo:
        def __init__(self, db):
            pass

        async def delete_user(self, tg_id):
            deleted.append(tg_id)
            return True

    monkeypatch.setattr(bot, "Repo", _FakeRepo)
    monkeypatch.setattr(bot, "get_sessionmaker", lambda: _fake_sessionmaker())
    bot.USER_STATES[USER_ID] = "что-то в памяти"
    bot._LAST_SEEN[USER_ID] = 1.0

    await bot.handle_message(_FakeUpdate(DELETE_CONFIRM), _FakeContext())

    assert deleted == [USER_ID]
    assert USER_ID not in bot.USER_STATES, "из памяти тоже надо убрать"
    assert USER_ID not in bot._LAST_SEEN


@pytest.mark.asyncio
async def test_delete_can_be_cancelled(monkeypatch):
    called = []

    class _FakeRepo:
        def __init__(self, db):
            pass

        async def delete_user(self, tg_id):
            called.append(tg_id)
            return True

    monkeypatch.setattr(bot, "Repo", _FakeRepo)
    _with_consent(monkeypatch)

    await bot.handle_message(_FakeUpdate(DELETE_CANCEL), _FakeContext())

    assert called == [], "отмена не должна ничего удалять"


@pytest.mark.asyncio
async def test_deletion_works_even_without_consent(monkeypatch):
    """
    Удалиться должно быть можно всегда — иначе человек, который отозвал согласие,
    не сможет попросить стереть уже собранное.
    """
    deleted = []

    class _FakeRepo:
        def __init__(self, db):
            pass

        async def delete_user(self, tg_id):
            deleted.append(tg_id)
            return True

    _no_consent(monkeypatch)
    monkeypatch.setattr(bot, "Repo", _FakeRepo)
    monkeypatch.setattr(bot, "get_sessionmaker", lambda: _fake_sessionmaker())

    await bot.handle_message(_FakeUpdate(DELETE_CONFIRM), _FakeContext())

    assert deleted == [USER_ID]


# --- разметка ---

def test_user_facing_texts_are_plain():
    """
    Регресс: экран согласия отправлялся с parse_mode="Markdown", а в тексте
    было непарное подчёркивание в «/delete_me» — Telegram отклонял сообщение
    целиком («Can't find end of Italic entity»). То есть самое первое сообщение
    новому пользователю не доходило.

    Теперь всё уходит простым текстом, значит любые markdown-символы человек
    увидит буквально.
    """
    from app.consent import CONSENT_TEXT, DECLINE_TEXT, NEED_CONSENT_TEXT
    from app.formatters import format_mbti
    from core.models import TraitScores
    from core.scoring import mbti_from_traits

    mbti = format_mbti(mbti_from_traits(TraitScores(
        extraversion=0.2, openness=0.2, agreeableness=0.8, conscientiousness=0.8)))

    for text in (CONSENT_TEXT, DECLINE_TEXT, NEED_CONSENT_TEXT, mbti):
        assert "**" not in text
        assert "__" not in text
