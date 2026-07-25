from __future__ import annotations

import uuid
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db.models import User, Session as DbSession, Signal, Synthesis, Akme, Message


def _strip_tz_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    """
    Excel не поддерживает timezone-aware datetime.
    Приводим все datetime64[ns, tz] -> datetime64[ns] (без tz).
    """
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_datetime64tz_dtype(df[col]):
            df[col] = df[col].dt.tz_convert(None)
    return df


async def export_session_full(db: AsyncSession, session_id: uuid.UUID, out_dir: str) -> dict[str, str]:
    """
    Выгрузка одной сессии в CSV + Excel:
    - sessions.csv
    - signals.csv
    - synthesis.csv
    - akme.csv
    и один Excel со вкладками.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # sessions + user
    sess_res = await db.execute(select(DbSession).where(DbSession.id == session_id))
    s = sess_res.scalar_one()

    user_res = await db.execute(select(User).where(User.telegram_id == s.user_id))
    u = user_res.scalar_one()

    sessions_df = pd.DataFrame([{
        "session_id": str(s.id),
        "telegram_id": u.telegram_id,
        "username": u.username,
        "started_at": s.started_at,
        "finished_at": s.finished_at,
        "validity_level_end": s.validity_level_end,
        "dialogue_saturated": s.dialogue_saturated,
        "status": s.status,
    }])

    # signals
    sig_res = await db.execute(select(Signal).where(Signal.session_id == session_id))
    sigs = sig_res.scalars().all()
    signals_df = pd.DataFrame([{
        "id": x.id,
        "session_id": str(x.session_id),
        "trait": x.trait,
        "direction": x.direction,
        "confidence": getattr(x, "confidence", None),
        "text": x.text,
        "direct_example": x.direct_example,
        "created_at": x.created_at,
    } for x in sigs])

    # messages
    msg_res = await db.execute(select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc()))
    msgs = msg_res.scalars().all()

    messages_df = pd.DataFrame([{
        "id": m.id,
        "session_id": str(m.session_id),
        "role": m.role,
        "source": m.source,
        "text": m.text,
        "created_at": m.created_at,
    } for m in msgs])


    # synthesis
    syn_res = await db.execute(select(Synthesis).where(Synthesis.session_id == session_id))
    syn = syn_res.scalar_one_or_none()
    synthesis_df = pd.DataFrame([{
        "session_id": str(session_id),
        "text": syn.text if syn else None,
        "traits_confidence": syn.traits_confidence if syn else None,
        "raw_json": syn.raw_json if syn else None,
        "created_at": syn.created_at if syn else None,
    }])

    # akme
    akme_res = await db.execute(select(Akme).where(Akme.session_id == session_id))
    ak = akme_res.scalar_one_or_none()
    akme_df = pd.DataFrame([{
        "session_id": str(session_id),
        "recommendations_text": ak.recommendations_text if ak else None,
        "vector_json": ak.vector_json if ak else None,
        "created_at": ak.created_at if ak else None,
    }])

    # CSV (в CSV timezone можно оставлять — это не проблема)
    sessions_csv = str(out / "sessions.csv")
    signals_csv = str(out / "signals.csv")
    synthesis_csv = str(out / "synthesis.csv")
    akme_csv = str(out / "akme.csv")

    sessions_df.to_csv(sessions_csv, index=False)
    signals_df.to_csv(signals_csv, index=False)
    synthesis_df.to_csv(synthesis_csv, index=False)
    akme_df.to_csv(akme_csv, index=False)
    messages_csv = str(out / "messages.csv")
    messages_df.to_csv(messages_csv, index=False)

    # Excel (обязательно убираем timezone)
    xlsx_path = str(out / "export.xlsx")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        sessions_x = _strip_tz_for_excel(sessions_df)
        signals_x = _strip_tz_for_excel(signals_df)
        synthesis_x = _strip_tz_for_excel(synthesis_df)
        akme_x = _strip_tz_for_excel(akme_df)
        messages_df = _strip_tz_for_excel(messages_df)
    
        sessions_x.to_excel(writer, sheet_name="sessions", index=False)
        signals_x.to_excel(writer, sheet_name="signals", index=False)
        synthesis_x.to_excel(writer, sheet_name="synthesis", index=False)
        akme_x.to_excel(writer, sheet_name="akme", index=False)
        messages_df.to_excel(writer, sheet_name="messages", index=False)

    return {
        "sessions_csv": sessions_csv,
        "signals_csv": signals_csv,
        "synthesis_csv": synthesis_csv,
        "akme_csv": akme_csv,
        "excel": xlsx_path,
        "messages_csv": messages_csv,
    }