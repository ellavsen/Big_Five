"""HTTP-слой для Telegram Mini App: отдаёт человеку его собственный профиль.

Отдельный процесс от бота — общая у них только база. Так перезапуск или падение
одного не трогает другой, и веб не тянет за собой ни LLM, ни распознавание речи.

Что здесь важно помнить:

- Кто спрашивает — решает только подпись Telegram (`app/webapp_auth.py`).
  Никаких `user_id` в параметрах запроса: профиль — спецкатегория ПДн.
- Наружу уходит только производное от синтеза. Сообщения разговора и сырые
  наблюдения не отдаются никогда, даже своему владельцу: незачем гонять их по сети.
- Четыре буквы считаются здесь же из черт, как и в боте. Второго источника типа
  быть не должно.
"""
from __future__ import annotations

import logging
import os

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.webapp_auth import InitDataError, verify_init_data
from core.config import WEBAPP_INIT_DATA_MAX_AGE
from core.db.database import get_sessionmaker
from core.db.repo import Repo
from core.models import TraitScores
from core.scoring import MBTI_MAPPING, mbti_from_traits
from modules.akme_vector import akme_vector_from_synthesis

logger = logging.getLogger(__name__)

# Сервер запускают через uvicorn, а не через app/main.py, поэтому .env читаем
# здесь же. Иначе токен окажется пустым и все запросы будут молча получать 401.
load_dotenv()

TRAIT_TITLES = {
    "openness": "Открытость опыту",
    "conscientiousness": "Добросовестность",
    "extraversion": "Экстраверсия",
    "agreeableness": "Доброжелательность",
    "neuroticism": "Реактивность на стресс",
}


class TraitOut(BaseModel):
    key: str
    title: str
    score: float
    confidence: float
    stability: str


class MbtiOut(BaseModel):
    letters: str
    is_complete: bool
    disclaimer: str
    sources: list[str]


class CoreVsRoleOut(BaseModel):
    core: list[str]
    role: list[str]


class AkmeOut(BaseModel):
    core: list[str]
    unload: list[str]
    environment: list[str]
    risk: list[str]


class ProfileOut(BaseModel):
    finished_at: str
    traits: list[TraitOut]
    mbti: MbtiOut
    core_vs_role: CoreVsRoleOut
    message: list[str]
    akme: AkmeOut


app = FastAPI(title="Neuro Mini App", docs_url=None, redoc_url=None)

# Витрина на GitHub Pages и Mini App — это один и тот же файл. Страница сама
# понимает, где её открыли: есть подпись Telegram — тянет профиль через API,
# нет — показывает демо-профиль. Копии нет, потому что копия разошлась бы
# с оригиналом при первой же правке.
PAGE = Path(__file__).resolve().parent.parent / "docs" / "index.html"


@app.get("/", include_in_schema=False)
async def page() -> FileResponse:
    # no-store: страница сама по себе публичная, но по ней сразу уходит запрос
    # за профилем, и незачем оставлять её в кэше на чужом устройстве.
    return FileResponse(PAGE, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})


def _authenticate(init_data: str) -> int:
    """Возвращает telegram_id или отказывает.

    Причина отказа уходит в лог, но не пользователю: подсказывать, что именно
    не сошлось, полезно только тому, кто подбирает.
    """
    try:
        user = verify_init_data(
            init_data,
            os.getenv("TELEGRAM_BOT_TOKEN", ""),
            WEBAPP_INIT_DATA_MAX_AGE,
        )
    except InitDataError as exc:
        logger.warning("Отказ в доступе к Mini App: %s", exc)
        raise HTTPException(status_code=401, detail="Не удалось подтвердить, кто вы") from exc

    return user.telegram_id


async def _load_profile(telegram_id: int) -> tuple[object, dict] | None:
    SessionMaker = get_sessionmaker()
    async with SessionMaker() as db:
        return await Repo(db).get_last_profile(telegram_id)


def _build_profile(finished_at, raw: dict) -> ProfileOut:
    scores = TraitScores.model_validate(raw.get("trait_scores") or {})
    confidence = raw.get("traits_confidence") or {}
    akme = akme_vector_from_synthesis(raw)
    mbti = mbti_from_traits(scores)

    traits = []
    for key, title in TRAIT_TITLES.items():
        # traits_confidence может не быть вовсе: у профиля старого формата
        # или когда модель его не вернула. Это не повод не показать черты.
        entry = confidence.get(key) or {}
        traits.append(
            TraitOut(
                key=key,
                title=title,
                score=getattr(scores, key),
                confidence=float(entry.get("confidence") or 0.0),
                stability=str(entry.get("stability") or "пограничная"),
            )
        )

    core_vs_role = raw.get("core_vs_role") or {}
    paragraphs = [p.strip() for p in str(raw.get("message") or "").split("\n\n") if p.strip()]

    return ProfileOut(
        finished_at=finished_at.isoformat() if hasattr(finished_at, "isoformat") else str(finished_at),
        traits=traits,
        mbti=MbtiOut(
            letters=mbti.letters,
            is_complete=mbti.is_complete,
            disclaimer=mbti.disclaimer,
            sources=[TRAIT_TITLES[trait].lower() for trait, _, _ in MBTI_MAPPING],
        ),
        core_vs_role=CoreVsRoleOut(
            core=[str(x) for x in (core_vs_role.get("core") or [])],
            role=[str(x) for x in (core_vs_role.get("role") or [])],
        ),
        message=paragraphs,
        akme=AkmeOut(
            core=akme.core,
            unload=akme.unload,
            environment=akme.environment,
            risk=akme.risk,
        ),
    )


@app.get("/api/profile", response_model=ProfileOut)
async def get_profile(
    # Заголовком, а не параметром адреса: адреса оседают в логах прокси,
    # в истории браузера и в Referer. Подписанной строке там не место.
    init_data: str = Header(default="", alias="X-Telegram-Init-Data"),
) -> ProfileOut:
    telegram_id = _authenticate(init_data)

    row = await _load_profile(telegram_id)
    if not row:
        raise HTTPException(status_code=404, detail="Профиля пока нет — сначала пройдите разговор в боте")

    finished_at, raw = row
    return _build_profile(finished_at, raw or {})
