"""Рекомендации должны быть действиями, а не ярлыками.

Человек, прошедший диалог, получил девятнадцать пунктов вида «выгорание из-за
накопления стресса» и «среда с балансом общения и уединения» — и сказал прямо:
это не рекомендации, я и так знаю, как у меня устроено. Ни один пункт не говорил,
что сделать в понедельник, и ни один не опирался на то, что человек рассказал.

Здесь проверяется детерминированный слой — тот, где формулировки в коде и я
за них отвечаю. То, что дописывает модель, держится промптом.
"""
import itertools

import pytest

from modules.akme_vector import akme_vector_from_synthesis

# Окончания повелительного наклонения: «ставь», «проси», «чередуй», «договаривайся».
# Существительные из старой версии — «организация», «выгорание», «среда»,
# «перегрузка», «потеря» — под них не попадают, и это ровно то, что нужно поймать.
IMPERATIVE_ENDINGS = ("й", "и", "ь", "ся", "йся")

# Момент, когда совет применять. Без него рекомендацию некуда приложить.
WHEN_MARKERS = (
    "раз в", "перед", "когда", "после", "в обед", "до того", "в день",
    "в неделю", "заранее", "в начале", "в тот же день", "сразу",
    "в течение дня", "в конце дня", "на конец", "по одному", "утром",
)

# Слова, которыми описывают состояние, а не действие. Целый пункт из таких —
# это ярлык. Список — из настоящей выдачи, которую забраковал человек.
LABEL_WORDS = (
    "выгорание", "перегрузка", "организация", "потеря контроля",
    "накопление стресса", "баланс общения",
)


def all_recommendations(synthesis: dict) -> list[str]:
    vector = akme_vector_from_synthesis(synthesis)
    return list(itertools.chain(vector.core, vector.unload, vector.environment, vector.risk))


def synthesis_with(**scores) -> dict:
    """Синтез без подсказок от модели: остаются только пункты из кода."""
    base = {
        "openness": 0.5, "conscientiousness": 0.5, "extraversion": 0.5,
        "agreeableness": 0.5, "neuroticism": 0.5,
    }
    base.update(scores)
    return {
        "trait_scores": base,
        "akme_vector": {"core": [], "unload": [], "environment": [], "risk": []},
        "core_vs_role": {"core": [], "role": []},
        "notes": [],
    }


# Все ветки эвристик: каждая черта в каждом из трёх положений.
ALL_BRANCHES = [
    pytest.param(synthesis_with(**{trait: value}), id=f"{trait}-{name}")
    for trait in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")
    for value, name in ((0.85, "высокая"), (0.15, "низкая"), (0.5, "средняя"))
]

WITH_EXTRAS = [
    pytest.param(
        {**synthesis_with(neuroticism=0.8), "core_vs_role": {"core": [], "role": ["контроль в проекте"]},
         "notes": ["compensation:control", "устал к концу недели"]},
        id="роль-и-заметки",
    ),
]


@pytest.mark.parametrize("synthesis", ALL_BRANCHES + WITH_EXTRAS)
def test_every_recommendation_starts_with_a_verb(synthesis):
    for item in all_recommendations(synthesis):
        first = item.split()[0].lower().strip("«»,.:—")
        assert first.endswith(IMPERATIVE_ENDINGS), (
            f"«{item[:60]}…» начинается с «{first}» — это не действие"
        )


@pytest.mark.parametrize("synthesis", ALL_BRANCHES + WITH_EXTRAS)
def test_every_recommendation_says_when(synthesis):
    for item in all_recommendations(synthesis):
        assert any(m in item.lower() for m in WHEN_MARKERS), (
            f"«{item[:60]}…» — непонятно, в какой момент это делать"
        )


@pytest.mark.parametrize("synthesis", ALL_BRANCHES + WITH_EXTRAS)
def test_no_recommendation_is_a_label(synthesis):
    for item in all_recommendations(synthesis):
        found = [w for w in LABEL_WORDS if w in item.lower()]
        assert not found, f"«{item[:60]}…» описывает состояние ({found}), а не действие"


@pytest.mark.parametrize("synthesis", ALL_BRANCHES)
def test_recommendations_fit_in_a_week(synthesis):
    """Пункт длиной в абзац человек не сделает. Ориентир — одна фраза."""
    for item in all_recommendations(synthesis):
        assert len(item) <= 130, f"слишком длинно ({len(item)}): {item[:70]}…"


def test_model_suggestions_are_kept_as_is():
    """То, что сформулировал синтезатор, остаётся — за его качество отвечает промпт."""
    synthesis = synthesis_with(conscientiousness=0.8)
    synthesis["akme_vector"]["unload"] = ["Передавай проверку качества, а не перепроверяй за всеми"]

    assert "Передавай проверку качества, а не перепроверяй за всеми" in akme_vector_from_synthesis(synthesis).unload


def test_every_branch_produces_something():
    """Пустой блок рекомендаций — тоже плохой ответ."""
    for param in ALL_BRANCHES:
        vector = akme_vector_from_synthesis(param.values[0])
        assert vector.core or vector.unload or vector.environment or vector.risk


# --- отсев пустышек от модели --------------------------------------------

@pytest.mark.parametrize("item", [
    "Обращай внимание на признаки истощения и злости",
    "Старайся не накапливать стресс в ситуациях, когда много мелких дел",
    "Создавай пространство для общения с близкими",
    "Поддерживай привычки, связанные с планированием",
    "Помни, что тебе нужно восстановление",
])
def test_empty_advice_from_the_model_is_dropped(item):
    """Формально глагол, а действия за ним нет.

    Промпт их запрещает, но живой прогон давал 2–3 таких из восьми пунктов
    в каждом ответе. Отсев в коде, а не надежда на дисциплину модели.
    """
    synthesis = synthesis_with()
    synthesis["akme_vector"]["unload"] = [item]

    assert item not in akme_vector_from_synthesis(synthesis).unload


@pytest.mark.parametrize("item", [
    "Проверяй в обед плечи, челюсть и дыхание",
    "Берись за важные дела в первой половине дня — ты сама говорила, что так голова работает лучше",
    "Ставь будильник на конец рабочего дня",
])
def test_real_advice_from_the_model_survives(item):
    synthesis = synthesis_with()
    synthesis["akme_vector"]["unload"] = [item]

    assert item in akme_vector_from_synthesis(synthesis).unload
