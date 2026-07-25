# modules/akme_vector.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from core.scoring import HIGH, LOW


@dataclass
class AkmeVector:
    core: List[str]
    unload: List[str]
    environment: List[str]
    risk: List[str]


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


def _level(scores: Dict[str, Any], trait: str) -> str:
    """high / low / mid. mid — данных не хватает или черта посередине."""
    value = float(scores.get(trait, 0.5) or 0.5)
    if value >= HIGH:
        return "high"
    if value <= LOW:
        return "low"
    return "mid"


def akme_vector_from_synthesis(synthesis: Dict[str, Any]) -> AkmeVector:
    """
    Делает практичный «вектор акме» из результата синтеза.

    Порядок: сначала берём то, что синтезатор сформулировал сам, потом мягко
    дополняем эвристиками по чертам. Считаем по OCEAN напрямую — MBTI здесь
    не участвует, он только для показа человеку.
    """
    synthesis = synthesis or {}

    raw_akme = synthesis.get("akme_vector") or {}
    if isinstance(raw_akme, dict):
        core = _as_list(raw_akme.get("core"))
        unload = _as_list(raw_akme.get("unload"))
        environment = _as_list(raw_akme.get("environment"))
        risk = _as_list(raw_akme.get("risk") or raw_akme.get("risks"))
    else:
        core, unload, environment, risk = [], [], [], []

    scores = synthesis.get("trait_scores", {}) or {}
    core_vs_role = synthesis.get("core_vs_role", {}) or {}
    notes = synthesis.get("notes", []) or []

    # 1) ядро и роль напрямую из синтеза
    core.extend(_as_list(core_vs_role.get("core")))
    if _as_list(core_vs_role.get("role")):
        risk.append("в ролевом режиме повышаются энергозатраты (есть признаки компенсации/усилия)")

    # 2) экстраверсия → как восстанавливаться и в какой среде
    extraversion = _level(scores, "extraversion")
    if extraversion == "low":
        unload.append("восстановление через тишину, одиночество, телесные ритуалы")
        environment.append("предсказуемая среда без постоянного социального давления")
    elif extraversion == "high":
        unload.append("восстановление через общение, совместные активности, обмен эмоциями")
        environment.append("команда/сообщество, где можно быть в контакте и обсуждать вслух")
    else:
        unload.append("сочетание контакта и уединения: дозировать общение и оставлять время на восстановление")
        environment.append("гибкая среда, где можно чередовать публичные и тихие задачи")

    # 3) открытость опыту → на каких задачах опираться
    openness = _level(scores, "openness")
    if openness == "high":
        core.append("задачи про смыслы, идеи, видение, стратегию и связи")
    elif openness == "low":
        core.append("задачи с ощутимым результатом, практические шаги, конкретика")
    else:
        core.append("чередование: конкретика ↔ смыслы (лучше работает в миксе)")

    # 4) доброжелательность → стиль коммуникации вокруг
    agreeableness = _level(scores, "agreeableness")
    if agreeableness == "high":
        environment.append("среда, где ценят эмпатию, поддержку и тонкость общения")
    elif agreeableness == "low":
        environment.append("коммуникация с ясными критериями, договорённостями и логикой решений")
    else:
        environment.append("среда, где уместны и логика, и эмпатия (баланс стилей)")

    # 5) добросовестность → ритм и что разгружать
    conscientiousness = _level(scores, "conscientiousness")
    if conscientiousness == "high":
        risk.append("риск перенапряжения из-за контроля и стремления «довести до конца»")
        unload.append("разгрузка через план + осознанные паузы (не только «ещё немного доделаю»)")
    elif conscientiousness == "low":
        risk.append("риск перегруза от хаоса/переключений и недозавершённости задач")
        unload.append("разгрузка через мягкие рамки, маленькие финалы и закрытие хвостов")
    else:
        unload.append("разгрузка через гибкий ритм: планировать опорные точки, но оставлять люфт")

    # 6) реактивность на стресс → то, ради чего заводилась пятая черта.
    # Раньше выгорание можно было упомянуть только если о нём случайно сказали в notes.
    neuroticism = _level(scores, "neuroticism")
    if neuroticism == "high":
        risk.append("высокая цена стрессовых периодов: усталость накапливается быстрее, чем уходит")
        unload.append("восстановление как обязательная часть плана, а не награда за сделанное")
        environment.append("предсказуемость и понятные ожидания заметно снижают фоновую нагрузку")
    elif neuroticism == "low":
        core.append("устойчивость под нагрузкой — на неё можно опираться в турбулентные периоды")
    else:
        unload.append("отслеживать ранние признаки усталости: они появляются раньше, чем становятся заметны")

    # 7) заметки → дополнительные риски
    for n in notes:
        s = str(n).lower()
        if "компенсац" in s:
            risk.append("следить за компенсациями: если часто «через силу» — нужен режим восстановления")
        if "выгора" in s or "устал" in s:
            risk.append("обратить внимание на ранние признаки усталости и профилактику выгорания")

    return AkmeVector(
        core=_uniq(core),
        unload=_uniq(unload),
        environment=_uniq(environment),
        risk=_uniq(risk),
    )
