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


# Глаголы-пустышки: формально повелительное наклонение, а действия за ними нет.
# Промпт их запрещает, но модель всё равно выдавала 2–3 таких из восьми пунктов
# в каждом прогоне. Поэтому отсев в коде, а не надежда на дисциплину.
EMPTY_ADVICE_OPENERS = (
    "обращай внимание",
    "уделяй внимание",
    "обрати внимание",
    "старайся",
    "постарайся",
    "поддерживай привычк",
    "создавай пространство",
    "прислушивайся",
    "помни",
    "не забывай",
    "позволяй себе",
    "следи за тем",
)


def is_actionable(text: str) -> bool:
    """Можно ли по фразе понять, что человек физически сделает.

    «Обращай внимание на усталость» — нельзя, это переформулированный диагноз.
    «Проверяй в обед плечи и челюсть» — можно.
    """
    return not text.strip().lower().startswith(EMPTY_ADVICE_OPENERS)


def _as_list(x: Any) -> List[str]:
    """Пункты от модели. Пустышки отсекаются здесь же — лучше короткий блок,
    чем блок, разбавленный «старайся не перегружаться»."""
    if not x:
        return []
    items = [str(i) for i in x] if isinstance(x, list) else [str(x)]
    return [i for i in items if i.strip() and is_actionable(i)]


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
    Делает «вектор акме» из результата синтеза.

    Порядок: сначала берём то, что синтезатор сформулировал сам, потом мягко
    дополняем эвристиками по чертам. Считаем по OCEAN напрямую — MBTI здесь
    не участвует, он только для показа человеку.

    ❗ **Каждый пункт — действие, а не ярлык.** Раньше здесь стояли описания
    состояний: «выгорание из-за накопления стресса», «организация и планирование
    дел», «среда с балансом общения и уединения». Человек, прошедший диалог,
    сказал прямо: это не рекомендации, я и так знаю, как у меня устроено.
    Он был прав — из девятнадцати выданных пунктов ни один не говорил,
    что сделать в понедельник.

    Признаки пункта, который годится:

    1. начинается с глагола в повелительном наклонении;
    2. содержит момент — когда именно это делать («перед тем как», «в обед»,
       «раз в неделю»), иначе совет некуда приложить;
    3. помещается в неделю: «ставь будильник на конец дня», а не «выстрой
       здоровые отношения с работой».

    Держится тестами в `tests/test_akme_actions.py`.
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

    # 1) роль напрямую из синтеза
    #
    # core_vs_role.core сюда НЕ подмешивается: это «устойчивое ядро личности»,
    # а блок подписан «на что опираться». Разные вещи. Из-за смешения под опорами
    # оказывалась «чувствительность к стрессу» — она действительно ядро, но
    # человеку сообщалось, что она его усиливает. На что опираться, синтезатор
    # пишет отдельным полем akme_vector.core, оно уже взято выше.
    if _as_list(core_vs_role.get("role")):
        risk.append(
            "Выписывай раз в неделю, что делалось «потому что надо», а не потому что хотелось — "
            "это и есть счёт за роль, без списка он не виден"
        )

    # 2) экстраверсия → как восстанавливаться и в какой среде
    extraversion = _level(scores, "extraversion")
    if extraversion == "low":
        unload.append("Ставь 20 минут тишины сразу после встреч, а не в конце дня")
        environment.append("Защищай один день в неделю без встреч так же, как защищаешь встречу")
    elif extraversion == "high":
        unload.append("Звони кому-то из своих, когда садятся силы, вместо того чтобы дотерпеть в одиночку")
        environment.append("Проси обсуждать задачу вслух в начале — так дешевле, чем разбирать переписку")
    else:
        unload.append("Дели день заранее на людную и тихую половину и не смешивай их")
        environment.append("Уточняй заранее, где нужно быть на связи, а где можно молча")

    # 3) открытость опыту → на каких задачах опираться
    openness = _level(scores, "openness")
    if openness == "high":
        core.append("Спрашивай «зачем это и что изменится» перед тем, как браться за задачу")
    elif openness == "low":
        core.append("Разбивай большое на шаги с видимым результатом и отмечай сделанное в тот же день")
    else:
        core.append("Чередуй в течение дня конкретную работу и задачи «про смысл» — подряд в одном режиме силы садятся")

    # 4) доброжелательность → стиль коммуникации вокруг
    agreeableness = _level(scores, "agreeableness")
    if agreeableness == "high":
        environment.append("Называй срок вслух, когда соглашаешься помочь: «да, но в четверг»")
    elif agreeableness == "low":
        environment.append("Фиксируй критерии готовности в начале работы — тогда спор идёт о них, а не о людях")
    else:
        environment.append("Договаривайся о способе решать споры заранее, до того как спор случился")

    # 5) добросовестность → ритм и что разгружать
    conscientiousness = _level(scores, "conscientiousness")
    if conscientiousness == "high":
        risk.append("Спрашивай себя перед перепроверкой чужой работы: «что сломается, если я не проверю?»")
        unload.append("Ставь будильник на конец рабочего дня и вставай по нему посреди «ещё немного доделаю»")
    elif conscientiousness == "low":
        risk.append("Держи один список хвостов и закрывай по одному в день, а не всё сразу")
        unload.append("Вычёркивай брошенное из списка заранее, чтобы оно не висело фоном")
    else:
        unload.append("Выбирай утром три главных дела на день, остальное — как получится")

    # 6) реактивность на стресс → то, ради чего заводилась пятая черта.
    # Раньше выгорание можно было упомянуть только если о нём случайно сказали в notes.
    neuroticism = _level(scores, "neuroticism")
    if neuroticism == "high":
        risk.append("Проверяй в обед плечи, челюсть и дыхание — так усталость ловится раньше, чем начнёт ломить тело")
        unload.append("Ставь восстановление в календарь до того, как раздашь день по задачам")
        environment.append("Проси называть срок и критерий готовности заранее: неопределённость стоит дороже самой работы")
    elif neuroticism == "low":
        core.append("Бери на себя трудный разговор, когда вокруг штормит: тебе он обходится дешевле, чем другим")
    else:
        unload.append("Отмечай раз в день одним словом, сколько осталось сил — через две недели увидишь, куда они уходят")

    # 7) заметки → дополнительные риски
    # «компенсац» не ловило ничего: модули пишут в notes латинское
    # `compensation:control`, а по-русски слово чаще звучит как «компенсаторной» —
    # там «сат», а не «сац». Правило было мёртвым с самого начала.
    compensation_markers = ("компенсац", "компенсатор", "compensation")
    tiredness_markers = ("выгора", "устал", "истощ")

    for n in notes:
        s = str(n).lower()
        if any(m in s for m in compensation_markers):
            risk.append("Лови фразу «надо потерпеть» и ставь себе десять минут паузы в тот же день")
        if any(m in s for m in tiredness_markers):
            risk.append("Выбери заранее один самый ранний признак усталости и реагируй на него, а не на третий по счёту")

    return AkmeVector(
        core=_uniq(core),
        unload=_uniq(unload),
        environment=_uniq(environment),
        risk=_uniq(risk),
    )
