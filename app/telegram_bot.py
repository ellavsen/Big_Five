import os
import uuid
import logging
import tempfile
import time
from dataclasses import asdict
from datetime import datetime
from pydantic import ValidationError
from telegram import ReplyKeyboardRemove, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from core.stt import STTClient
from app.buttons import BASE_KB, AFTER_SYNTH_KB, SYNTH_CONFIRM_KB, VOICE_KB
from app.consent import (
    AGREE, DECLINE, DELETE_CANCEL, DELETE_CONFIRM,
    CONSENT_CHANGED_TEXT, CONSENT_KB, CONSENT_TEXT, DECLINE_TEXT,
    DELETE_KB, NEED_CONSENT_TEXT,
)
from app.formatters import format_akme
from modules.akme_vector import akme_vector_from_synthesis

from core.orchestrator import Orchestrator
from core.models import ConversationState, PreviousProfile, TraitScores
from core.scoring import mbti_from_traits
from core.llm import AsyncLLMClient
from core.utils import load_text
from core.config import CONSENT_VERSION, RETENTION_DAYS

from core.db.database import get_sessionmaker, init_db
from core.db.repo import Repo
from core.db.export import export_session_full


HELP_TEXT = (
    "Мы просто разговариваем, я аккуратно собираю наблюдения.\n"
    "Когда данных будет достаточно — я сам предложу подвести итог 🙂\n\n"
    "Команды:\n"
    "/start — начать\n"
    "/akme — практические рекомендации (после итога)\n"
    "/export — выгрузка текущей сессии в Excel\n"
    "/reset — сброс\n"
    "/delete_me — удалить все мои данные\n"
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# httpx на INFO печатает полный URL запроса, а токен бота у Telegram лежит прямо
# в пути: /bot<ТОКЕН>/getUpdates. То есть любой лог, приложенный к issue или
# отправленный в поддержку, отдавал вместе с собой полный доступ к боту.
logging.getLogger("httpx").setLevel(logging.WARNING)

# Горячий кэш активных диалогов. Долговременное хранилище — sessions.state_json,
# отсюда состояние можно выбрасывать: _get_state поднимет его обратно из БД.
USER_STATES: dict[int, ConversationState] = {}
_LAST_SEEN: dict[int, float] = {}

# Час без сообщений — диалог уходит из памяти. Лежит в отдельном словаре, а не
# внутри USER_STATES, чтобы состояние оставалось просто ConversationState.
STATE_TTL_SECONDS = 3600


# ----------------------------
# helpers
# ----------------------------

def _state_from_snapshot(session_id: uuid.UUID, snapshot: dict | None) -> ConversationState:
    """
    Собирает состояние по строке БД. Снимок бывает пустым (сессия создана, но процесс
    упал до первого хода) или несовместимым (контракт состояния менялся между версиями) —
    в обоих случаях берём чистое состояние, но переиспользуем сессию, чтобы не плодить
    в БД брошенные active-сессии.
    """
    if snapshot:
        try:
            return ConversationState.model_validate(snapshot)
        except ValidationError as e:
            logger.warning("Снимок сессии %s не читается (%s), начинаем с чистого состояния", session_id, e)

    return ConversationState(session_id=str(session_id))


async def _rehydrate_state(user_id: int) -> ConversationState | None:
    """Достаёт активный диалог из БД. None — если такого нет."""
    SessionMaker = get_sessionmaker()
    async with SessionMaker() as db:
        row = await Repo(db).get_active_session(user_id)

    if row is None:
        return None

    session_id, snapshot = row
    state = _state_from_snapshot(session_id, snapshot)
    logger.info("Восстановлен диалог пользователя %s из сессии %s", user_id, session_id)
    return state


def _evict_stale_states(now: float | None = None) -> list[int]:
    """
    Выбрасывает из памяти диалоги, в которых давно не писали.

    Выбрасываем только те, у которых есть session_id: без него состояние ни разу
    не доехало до БД, и rehydrate его уже не вернёт. Такое молча терять нельзя.
    """
    now = time.monotonic() if now is None else now
    cutoff = now - STATE_TTL_SECONDS

    stale = [
        uid for uid, seen in _LAST_SEEN.items()
        if seen < cutoff and (USER_STATES.get(uid) is None or USER_STATES[uid].session_id)
    ]
    for uid in stale:
        USER_STATES.pop(uid, None)
        _LAST_SEEN.pop(uid, None)

    if stale:
        logger.info("Выгружено из памяти неактивных диалогов: %d", len(stale))
    return stale


def _put_fresh_state(user_id: int) -> ConversationState:
    """
    Кладёт в память чистое состояние (/start, сброс). Обязательно отмечает время:
    записи без отметки уборщик не видит и они остаются в памяти навсегда.
    """
    state = ConversationState()
    USER_STATES[user_id] = state
    _LAST_SEEN[user_id] = time.monotonic()
    return state


async def _get_state(user_id: int) -> ConversationState:
    _evict_stale_states()

    state = USER_STATES.get(user_id)
    if state is None:
        state = await _rehydrate_state(user_id) or ConversationState()
        USER_STATES[user_id] = state

    _LAST_SEEN[user_id] = time.monotonic()
    return state

async def _save_message_to_db(state: ConversationState, role: str, text: str, source: str = "text"):
    if not state.session_id:
        return
    SessionMaker = get_sessionmaker()
    async with SessionMaker() as db:
        repo = Repo(db)
        await repo.add_message(uuid.UUID(state.session_id), role=role, text=text, source=source)

async def _has_consent(tg_id: int) -> bool:
    """
    Дал ли человек согласие на действующую редакцию.

    Единственное, что мы знаем о нём до согласия, — telegram_id: иначе согласие
    не к чему привязать. Всё остальное собирается только после «да».
    """
    SessionMaker = get_sessionmaker()
    async with SessionMaker() as db:
        version = await Repo(db).get_consent_version(tg_id)

    return version == CONSENT_VERSION


async def _ask_for_consent(update: Update, changed: bool = False) -> None:
    text = (CONSENT_CHANGED_TEXT + "\n\n" + CONSENT_TEXT) if changed else CONSENT_TEXT
    await update.message.reply_text(text, reply_markup=CONSENT_KB)


def _previous_profile_from_row(row: tuple[datetime, dict] | None) -> PreviousProfile | None:
    """
    Строка из БД → компактная память о прошлом разговоре.

    Прошлый итог мог быть сохранён другой версией контракта — тогда просто нет
    памяти, а не сломанный диалог.
    """
    if row is None:
        return None

    finished_at, raw = row
    if not isinstance(raw, dict):
        return None

    try:
        return PreviousProfile(
            finished_at=finished_at.date().isoformat(),
            trait_scores=TraitScores.model_validate(raw.get("trait_scores") or {}),
            notes=[str(n) for n in (raw.get("notes") or [])][:5],
        )
    except ValidationError as e:
        logger.warning("Прошлый профиль не читается (%s), начинаем без памяти", e)
        return None


async def _ensure_db_session_for_user(state: ConversationState, tg_id: int, username: str | None) -> None:
    """
    Гарантирует, что в state есть telegram_id и session_id.
    Если session_id нет — создаёт новую сессию в БД.
    """
    state.telegram_id = tg_id

    if state.session_id:
        return

    SessionMaker = get_sessionmaker()
    async with SessionMaker() as db:
        repo = Repo(db)
        await repo.upsert_user(tg_id, username)
        # прошлый профиль читаем ДО создания новой сессии — она ещё без итога,
        # так что запрос заведомо не подхватит сам себя
        previous = await repo.get_last_profile(tg_id)
        sid = await repo.create_session(tg_id)
        state.session_id = str(sid)

    state.previous_profile = _previous_profile_from_row(previous)
    if state.previous_profile:
        logger.info("Пользователь %s: подтянут профиль от %s",
                    tg_id, state.previous_profile.finished_at)

    # если есть поле для дельты — инициализируем
    if hasattr(state, "last_saved_signals_count"):
        state.last_saved_signals_count = 0


def _signals_payload_from_state(state: ConversationState) -> list[dict]:
    """
    Превращает state.evidence.signals в список dict для repo.add_signals()
    """
    payload = []
    for s in getattr(state.evidence, "signals", []):
        payload.append(
            {
                "trait": s.trait.value,
                "direction": s.direction.value,
                "confidence": float(s.confidence),
                "text": s.text,
                "direct_example": bool(s.direct_example),
            }
        )
    return payload


async def _persist_step_state(state: ConversationState) -> None:
    """
    Сохраняем в БД:
    - sessions(validity, saturated)
    - новые signals
    """
    if not state.session_id:
        return

    sid = uuid.UUID(state.session_id)

    # 1) sessions
    SessionMaker = get_sessionmaker()
    async with SessionMaker() as db:
        repo = Repo(db)
        await repo.touch_session_state(
            sid,
            validity_level=state.validity_level,
            dialogue_saturated=bool(getattr(state, "dialogue_saturated", False)),
            state_json=state.model_dump(mode="json"),
        )

    # 2) signals
    all_signals = _signals_payload_from_state(state)

    # если есть last_saved_signals_count — пишем только новые
    if hasattr(state, "last_saved_signals_count"):
        start_idx = int(getattr(state, "last_saved_signals_count", 0))
        new_signals = all_signals[start_idx:]
        state.last_saved_signals_count = len(all_signals)
    else:
        # fallback: пишем всё, а дубль отфильтрует UNIQUE + rollback в repo
        new_signals = all_signals

    if new_signals:
        SessionMaker = get_sessionmaker()
        async with SessionMaker() as db:
            repo = Repo(db)
            await repo.add_signals(sid, new_signals)


async def _persist_synthesis_and_finish(state: ConversationState, synthesis_text: str) -> None:
    """
    Сохраняем synthesis + закрываем session.
    """
    if not state.session_id:
        return

    sid = uuid.UUID(state.session_id)

    raw_json = state.synthesis if isinstance(state.synthesis, dict) else None
    traits_conf = None
    if isinstance(raw_json, dict):
        traits_conf = raw_json.get("traits_confidence")

    SessionMaker = get_sessionmaker()
    async with SessionMaker() as db:
        repo = Repo(db)
        await repo.save_synthesis(
            sid,
            text=synthesis_text,
            traits_confidence=traits_conf,
            raw_json=raw_json,
        )
        await repo.finish_session(
            sid,
            validity_level_end=state.validity_level,
            dialogue_saturated=bool(getattr(state, "dialogue_saturated", False)),
            status="finished",
        )


async def _persist_akme(state: ConversationState, recommendations_text: str, vector_json: dict | None) -> None:
    if not state.session_id:
        return
    sid = uuid.UUID(state.session_id)
    SessionMaker = get_sessionmaker()
    async with SessionMaker() as db:
        repo = Repo(db)
        await repo.save_akme(
            sid,
            recommendations_text=recommendations_text,
            vector_json=vector_json,
        )


# ----------------------------
# handlers
# ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user

    if not await _has_consent(tg.id):
        await _ask_for_consent(update)
        return

    await _begin_conversation(update, tg)


async def _begin_conversation(update: Update, tg) -> None:
    """Начинает разговор. Вызывается только когда согласие уже есть."""
    state = _put_fresh_state(tg.id)

    # закрываем прошлую активную сессию, иначе они копятся вечно
    await _close_active_session(tg.id, status="reset")
    await _ensure_db_session_for_user(state, tg.id, tg.username)

    await update.message.reply_text(
        "Привет! Я помогу мягко исследовать твой стиль мышления и восстановления.\n"
        "Можем просто поговорить 🙂",
        reply_markup=BASE_KB
    )


async def _close_active_session(tg_id: int, status: str) -> None:
    """Закрывает незавершённую сессию пользователя, если она была."""
    SessionMaker = get_sessionmaker()
    async with SessionMaker() as db:
        repo = Repo(db)
        row = await repo.get_active_session(tg_id)
        if row:
            await repo.finish_session(row[0], validity_level_end=None,
                                      dialogue_saturated=False, status=status)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = (update.message.text or "").strip()
    tg = update.effective_user

    # --- СОГЛАСИЕ: до него ничего не сохраняем и не зовём LLM ---

    if text == AGREE:
        SessionMaker = get_sessionmaker()
        async with SessionMaker() as db:
            await Repo(db).set_consent(tg.id, tg.username, CONSENT_VERSION)
        logger.info("Пользователь %s дал согласие, редакция %s", tg.id, CONSENT_VERSION)
        await _begin_conversation(update, tg)
        return

    if text == DELETE_CONFIRM:
        await _delete_everything(update, tg.id)
        return

    if text == DELETE_CANCEL:
        await update.message.reply_text("Ничего не удаляю 🙂", reply_markup=BASE_KB)
        return

    if text == DECLINE:
        await update.message.reply_text(DECLINE_TEXT, reply_markup=ReplyKeyboardRemove())
        return

    if not await _has_consent(tg.id):
        await update.message.reply_text(NEED_CONSENT_TEXT, reply_markup=ReplyKeyboardRemove())
        return

    if text == "ℹ️ Помощь":
        await update.message.reply_text(HELP_TEXT, reply_markup=BASE_KB)
        return

    state = await _get_state(user_id)
    orchestrator: Orchestrator = context.bot_data["orchestrator"]

    await _ensure_db_session_for_user(state, tg.id, tg.username)

    # --- КНОПКИ УПРАВЛЕНИЯ ---

    if text == "🔁 Сброс":
        # закрываем текущую сессию как reset (если была)
        if state.session_id:
            sid = uuid.UUID(state.session_id)
            SessionMaker = get_sessionmaker()
            async with SessionMaker() as db:
                repo = Repo(db)
                await repo.finish_session(
                    sid,
                    validity_level_end=state.validity_level,
                    dialogue_saturated=bool(getattr(state, "dialogue_saturated", False)),
                    status="reset",
                )

        state = _put_fresh_state(user_id)
        await _ensure_db_session_for_user(state, tg.id, tg.username)

        await update.message.reply_text("Ок! Начнём заново 🙂", reply_markup=BASE_KB)
        return

    if text == "📝 Показать распознанный текст":
        if not state.last_transcript:
            await update.message.reply_text(
                "Пока нет распознанного текста 🙂 Пришли голосовое сообщение.",
                reply_markup=BASE_KB
            )
            return

        state.awaiting_transcript_fix = True
        await update.message.reply_text(
            "Вот что я распознала из аудио:\n\n"
            f"“{state.last_transcript}”\n\n"
            "Если хочешь исправить — просто отправь правильный текст следующим сообщением.",
            reply_markup=BASE_KB
        )
        return
    
    # --- ПОДТВЕРЖДЕНИЕ ИТОГА ---

    if text == "✅ Подвести итог":
        state.synthesis_confirmed = True

        response = await orchestrator.step(state, "")

        # сохраняем step state (signals + sessions)
        await _persist_step_state(state)

        # если orchestration реально вернул синтез — сохраняем synthesis и завершаем session
        if response.A == "synthesize":
            await _persist_synthesis_and_finish(state, response.message)

        await update.message.reply_text(response.message, reply_markup=AFTER_SYNTH_KB)
        await _save_message_to_db(state, role="assistant", text=response.message, source="system")
        return

    if text == "↩️ Продолжим разговор":
        state.synthesis_confirmed = False
        reply = "Хорошо, продолжаем 🙂"
        await update.message.reply_text(reply, reply_markup=BASE_KB)
        await _save_message_to_db(state, role="assistant", text=reply, source="system")
        return

    # --- АКМЕ ---

    if text == "🧭 Практические рекомендации":
        await akme_cmd(update, context)
        return
    
    if state.awaiting_transcript_fix:
        state.awaiting_transcript_fix = False
        fixed_text = text.strip()

        if len(fixed_text) < 2:
            await update.message.reply_text(
                "Исправление слишком короткое 🙂 Напиши чуть подробнее.",
                reply_markup=BASE_KB
            )
            return

    # заменяем последний transcript на исправленный
        state.last_transcript = fixed_text
        await _save_message_to_db(state, role="user", text=fixed_text, source="transcript_fix")

        response = await orchestrator.step(state, fixed_text)
        await _persist_step_state(state)

        if response.A == "synthesize":
            await _persist_synthesis_and_finish(state, response.message)
            await update.message.reply_text(response.message, reply_markup=AFTER_SYNTH_KB)
            await _save_message_to_db(state, role="assistant", text=response.message, source="system")
            return

        await update.message.reply_text(response.message, reply_markup=BASE_KB)
        await _save_message_to_db(state, role="assistant", text=response.message, source="system")
        return

    # --- ОСНОВНОЙ ХОД ---
    # если это обычный текст пользователя — сохраняем
    await _save_message_to_db(state, role="user", text=text, source="text") 
    response = await orchestrator.step(state, text)

    # persist after each step
    await _persist_step_state(state)

    # ЕСЛИ orchestrator спрашивает про итог — показываем кнопки подтверждения
    if (
        response.A == "ask"
        and bool(getattr(state, "dialogue_saturated", False))
        and not state.synthesis_confirmed
        and not state.synthesis
    ):
        await update.message.reply_text(response.message, reply_markup=SYNTH_CONFIRM_KB)
        await _save_message_to_db(state, role="assistant", text=response.message, source="system")
        return

    # ЕСЛИ это синтез — показываем кнопки после итога + сохраняем БД
    if response.A == "synthesize":
        await _persist_synthesis_and_finish(state, response.message)
        await update.message.reply_text(response.message, reply_markup=AFTER_SYNTH_KB)
        await _save_message_to_db(state, role="assistant", text=response.message, source="system")
        return

    # ОБЫЧНЫЙ ОТВЕТ
    await update.message.reply_text(response.message, reply_markup=BASE_KB)
    await _save_message_to_db(state, role="assistant", text=response.message, source="system")


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tg = update.effective_user

    if not await _has_consent(tg.id):
        await update.message.reply_text(NEED_CONSENT_TEXT, reply_markup=ReplyKeyboardRemove())
        return

    state = await _get_state(user_id)
    orchestrator: Orchestrator = context.bot_data["orchestrator"]
    await _ensure_db_session_for_user(state, tg.id, tg.username)

    # 1) достаём voice/audio
    file_id = None
    if update.message.voice:
        file_id = update.message.voice.file_id
    elif update.message.audio:
        file_id = update.message.audio.file_id

    if not file_id:
        await update.message.reply_text("Не получилось прочитать аудио 😕", reply_markup=BASE_KB)
        return

    # 2) скачиваем файл
    tg_file = await context.bot.get_file(file_id)

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "input.ogg")
        await tg_file.download_to_drive(audio_path)

        # 3) распознаём
        text = await context.bot_data["stt"].transcribe(audio_path)

    text = (text or "").strip()
    if len(text) < 2:
        await update.message.reply_text(
            "Я почти ничего не расслышала. Можешь повторить чуть громче или подольше? 🙂",
            reply_markup=BASE_KB
        )
        return
    state.last_transcript = text
    state.awaiting_transcript_fix = False
    await _save_message_to_db(state, role="user", text=text, source="voice_transcript")
    # (опционально) показать распознанный текст
    # await update.message.reply_text(f"Я услышала так:\n\n{text}", reply_markup=BASE_KB)

    # 4) дальше как обычный текст
    response = await orchestrator.step(state, text)
    await _persist_step_state(state)

    if (
        response.A == "ask"
        and state.dialogue_saturated
        and not state.synthesis_confirmed
        and not state.synthesis
    ):
        await update.message.reply_text(response.message, reply_markup=SYNTH_CONFIRM_KB)
        await _save_message_to_db(state, role="assistant", text=response.message, source="system")
        return

    if response.A == "synthesize":
        await _persist_synthesis_and_finish(state, response.message)
        await update.message.reply_text(response.message, reply_markup=AFTER_SYNTH_KB)
        await _save_message_to_db(state, role="assistant", text=response.message, source="system")
        return
    await update.message.reply_text(
        response.message,
        reply_markup=VOICE_KB
    )
    await _save_message_to_db(state, role="assistant", text=response.message, source="system")
async def akme_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = await _get_state(user_id)

    tg = update.effective_user
    await _ensure_db_session_for_user(state, tg.id, tg.username)

    if not state.synthesis:
        await update.message.reply_text(
            "Пока рано: у меня ещё нет итогового синтеза. "
            "Давай чуть продолжим разговор — и я подведу итог, после чего появятся рекомендации 🙂",
            reply_markup=BASE_KB
        )
        return
    
    akme = akme_vector_from_synthesis(state.synthesis)
    # четыре буквы считаем из черт, а не берём probabilities из ответа модели:
    # ядро — Big Five, и второй источник типа спорил бы с ним
    scores = TraitScores.model_validate(state.synthesis.get("trait_scores") or {})
    text = format_akme(akme, mbti=mbti_from_traits(scores))

    await _persist_akme(state, recommendations_text=text, vector_json=asdict(akme))

    await update.message.reply_text(text, reply_markup=AFTER_SYNTH_KB)


async def delete_me_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Право на удаление. Шаг 1: предупреждаем, что это безвозвратно."""
    await update.message.reply_text(
        "Это удалит ВСЁ: наши сообщения, собранные наблюдения, профиль "
        "и рекомендации. Восстановить будет нельзя.\n\n"
        "Точно удаляем?",
        reply_markup=DELETE_KB,
    )


async def _delete_everything(update: Update, tg_id: int) -> None:
    """Шаг 2: сносим пользователя, каскад забирает всё остальное."""
    SessionMaker = get_sessionmaker()
    async with SessionMaker() as db:
        deleted = await Repo(db).delete_user(tg_id)

    USER_STATES.pop(tg_id, None)
    _LAST_SEEN.pop(tg_id, None)
    logger.info("Данные пользователя %s удалены по запросу (было что удалять: %s)", tg_id, deleted)

    await update.message.reply_text(
        "Готово. Все данные удалены.\n\n"
        "Если захочешь начать заново — /start.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = await _get_state(user_id)

    # закрываем текущую сессию как reset (если была)
    if state.session_id:
        sid = uuid.UUID(state.session_id)
        SessionMaker = get_sessionmaker()
        async with SessionMaker() as db:
            repo = Repo(db)
            await repo.finish_session(
                sid,
                validity_level_end=state.validity_level,
                dialogue_saturated=bool(getattr(state, "dialogue_saturated", False)),
                status="reset",
            )

    state = _put_fresh_state(user_id)

    tg = update.effective_user
    await _ensure_db_session_for_user(state, tg.id, tg.username)

    await update.message.reply_text("Состояние сброшено. Начнём заново 🙂", reply_markup=BASE_KB)


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /export — выгрузка текущей сессии в Excel + CSV.
    Доступно всем (MVP).
    """
    user_id = update.effective_user.id
    state = await _get_state(user_id)

    if not state.session_id:
        await update.message.reply_text("Нет активной сессии для экспорта. Нажми /start 🙂", reply_markup=BASE_KB)
        return

    sid = uuid.UUID(state.session_id)

    await update.message.reply_text("Готовлю выгрузку…", reply_markup=BASE_KB)

    SessionMaker = get_sessionmaker()
    async with SessionMaker() as db:
        paths = await export_session_full(db, sid, out_dir=f"exports/{state.session_id}")

    xlsx_path = paths["excel"]

    # отправляем Excel
    try:
        with open(xlsx_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=f"session_{state.session_id}.xlsx",
                caption="Экспорт сессии (Excel): sessions / signals / synthesis / akme",
            )
    except Exception as e:
        logger.exception("Failed to send export")
        await update.message.reply_text(f"Не смогла отправить файл: {e}", reply_markup=BASE_KB)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception", exc_info=context.error)
    # не спамим пользователю деталями, но даём понятный фидбек
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Ой, у меня произошла внутренняя ошибка 🙈\n"
            "Попробуй повторить действие или нажми «🔁 Сброс».",
            reply_markup=BASE_KB
        )


def run_bot():
    llm = AsyncLLMClient()
    orchestrator = Orchestrator(
        llm=llm,
        turn_planner_prompt=load_text("prompts/turn_planner.md"),
        synthesizer_prompt=load_text("prompts/synthesizer.md"),
    )

    app = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    app.bot_data["orchestrator"] = orchestrator
    app.bot_data["stt"] = STTClient()

    async def _post_init(application):
        await init_db()

        # Ретеншен на старте процесса. Это половина решения: пока бот не
        # перезапускают, просроченное лежит. В проде нужен cron или воркер —
        # см. docs/ROADMAP.md.
        SessionMaker = get_sessionmaker()
        async with SessionMaker() as db:
            removed = await Repo(db).delete_expired_sessions(RETENTION_DAYS)
        if removed:
            logger.info("Ретеншен: удалено сессий старше %d дней: %d", RETENTION_DAYS, removed)

    app.post_init = _post_init

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("akme", akme_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("delete_me", delete_me_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_audio))
    app.add_error_handler(error_handler)

    app.run_polling()