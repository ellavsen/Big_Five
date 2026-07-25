# modules/akme_vector.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class AkmeVector:
    core: List[str]
    unload: List[str]
    environment: List[str]
    risk: List[str]


def _dominant_letter(axis: str, value: float) -> str:
    """
    value интерпретируем как долю "первой буквы" в паре:
    EI: доля I
    SN: доля S
    TF: доля T
    JP: доля J
    """
    if axis == "EI":
        first, second = "I", "E"
    elif axis == "SN":
        first, second = "S", "N"
    elif axis == "TF":
        first, second = "T", "F"
    elif axis == "JP":
        first, second = "J", "P"
    else:
        return "?"

    if value >= 0.6:
        return first
    if value <= 0.4:
        return second
    return "X"


def _uniq(xs: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in xs:
        x = (x or "").strip()
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _as_list(x: Any) -> List[str]:
    if not x:
        return []
    if isinstance(x, list):
        return [str(i) for i in x if str(i).strip()]
    return [str(x)]


def akme_vector_from_synthesis(synthesis: Dict[str, Any]) -> AkmeVector:
    """
    Делает практичный 'вектор акме' по результату synthesize.

    ВАЖНО:
    - Если synthesizer уже вернул готовый akme_vector — мы его используем.
    - Затем мягко дополняем недостающие поля эвристиками.
    """
    synthesis = synthesis or {}

    # 0) Базовый akme_vector из синтеза (если есть)
    raw_akme = synthesis.get("akme_vector") or {}
    if isinstance(raw_akme, dict):
        base_core = _as_list(raw_akme.get("core"))
        base_unload = _as_list(raw_akme.get("unload"))
        base_env = _as_list(raw_akme.get("environment"))
        # поддержка risk/risks на всякий случай
        base_risk = _as_list(raw_akme.get("risk") or raw_akme.get("risks"))
    else:
        base_core, base_unload, base_env, base_risk = [], [], [], []

    axis_map = synthesis.get("axis_map", {}) or {}
    core_vs_role = synthesis.get("core_vs_role", {}) or {}
    notes = synthesis.get("notes", []) or []

    core: List[str] = list(base_core)
    unload: List[str] = list(base_unload)
    environment: List[str] = list(base_env)
    risk: List[str] = list(base_risk)

    # 1) CORE / ROLE напрямую из синтеза
    core.extend(_as_list(core_vs_role.get("core")))
    role = _as_list(core_vs_role.get("role"))
    if role:
        risk.append("в ролевом режиме повышаются энергозатраты (есть признаки компенсации/усилия)")

    # 2) Оси → рекомендации (добавляем только если чего-то не хватает)
    ei = float(axis_map.get("EI", 0.5) or 0.5)
    sn = float(axis_map.get("SN", 0.5) or 0.5)
    tf = float(axis_map.get("TF", 0.5) or 0.5)
    jp = float(axis_map.get("JP", 0.5) or 0.5)

    EI = _dominant_letter("EI", ei)
    SN = _dominant_letter("SN", sn)
    TF = _dominant_letter("TF", tf)
    JP = _dominant_letter("JP", jp)

    # EI: разгрузка и среда
    if not unload or not environment:
        if EI == "I":
            unload.append("восстановление через тишину, одиночество, телесные ритуалы")
            environment.append("предсказуемая среда без постоянного социального давления")
        elif EI == "E":
            unload.append("восстановление через общение, совместные активности, обмен эмоциями")
            environment.append("команда/сообщество, где можно быть в контакте и обсуждать вслух")
        else:
            unload.append("сочетание контакта и уединения: дозировать общение и оставлять время на восстановление")
            environment.append("гибкая среда, где можно чередовать публичные и тихие задачи")

    # SN: фокус задач
    if SN == "S":
        core.append("задачи с ощутимым результатом, практические шаги, конкретика")
    elif SN == "N":
        core.append("задачи про смыслы, идеи, видение, стратегию и связи")
    else:
        core.append("чередование: конкретика ↔ смыслы (лучше работает в миксе)")

    # TF: принятие решений и коммуникация
    if TF == "T":
        environment.append("коммуникация с ясными критериями, договорённостями и логикой решений")
    elif TF == "F":
        environment.append("среда, где ценят эмпатию, поддержку и тонкость общения")
    else:
        environment.append("среда, где уместны и логика, и эмпатия (баланс стилей)")

    # JP: ритм и риск выгорания
    if JP == "J":
        risk.append("риск перенапряжения из-за контроля и стремления 'довести до конца'")
        unload.append("разгрузка через план + осознанные паузы (не только 'ещё немного доделаю')")
    elif JP == "P":
        risk.append("риск перегруза от хаоса/переключений и недозавершённости задач")
        unload.append("разгрузка через мягкие рамки, маленькие финалы и закрытие хвостов")
    else:
        unload.append("разгрузка через гибкий ритм: планировать опорные точки, но оставлять люфт")

    # 3) заметки → риск/подсказки
    for n in notes:
        s = str(n).lower()
        if "компенсац" in s:
            risk.append("следить за компенсациями: если часто 'через силу' — нужен режим восстановления")
        if "выгора" in s or "устал" in s:
            risk.append("обратить внимание на ранние признаки усталости и профилактику выгорания")

    return AkmeVector(
        core=_uniq(core),
        unload=_uniq(unload),
        environment=_uniq(environment),
        risk=_uniq(risk),
    )
