import pytest

from core.models import SynthesisResult, TraitScores
from core.scoring import mbti_from_traits
from modules.akme_vector import akme_vector_from_synthesis


# --- MBTI как производная от черт ---

def test_mbti_is_derived_from_traits():
    """
    Ядро — OCEAN, четыре буквы выводятся из него. Neuroticism в них не входит:
    пары в MBTI у него нет, и подменять его похожим было бы враньём.
    """
    reading = mbti_from_traits(TraitScores(
        extraversion=0.18,        # низкая -> I
        openness=0.38,            # низкая -> S
        agreeableness=0.79,       # высокая -> F
        conscientiousness=0.85,   # высокая -> J
        neuroticism=0.66,         # в буквы не попадает
    ))

    assert reading.letters == "ISFJ"
    assert reading.is_complete is True
    assert "не результат" in reading.disclaimer


def test_undecided_trait_shows_x_instead_of_being_forced():
    reading = mbti_from_traits(TraitScores(extraversion=0.5))

    assert reading.letters[0] == "X"
    assert reading.is_complete is False


def test_neuroticism_does_not_change_the_letters():
    calm = mbti_from_traits(TraitScores(neuroticism=0.05)).letters
    stressed = mbti_from_traits(TraitScores(neuroticism=0.95)).letters

    assert calm == stressed


# --- akme считается по чертам ---

def test_akme_vector_from_llm_synthesis():
    """На вход идёт результат синтезатора (trait_scores / core_vs_role / akme_vector)."""
    synthesis = {
        "message": "связный текст",
        "trait_scores": {"extraversion": 0.2, "openness": 0.2,
                         "agreeableness": 0.7, "conscientiousness": 0.9,
                         "neuroticism": 0.5},
        "core_vs_role": {
            "core": ["самостоятельный анализ"],
            "role": ["повышенный контроль"],
        },
        "notes": ["часть контроля выглядит компенсаторной"],
        "akme_vector": {
            "core": ["роли с аналитической ответственностью"],
            "unload": ["избыточный контроль процессов"],
        },
    }

    akme = akme_vector_from_synthesis(synthesis)

    # опоры берутся из akme_vector.core, а не из core_vs_role.core
    assert "роли с аналитической ответственностью" in akme.core
    assert "самостоятельный анализ" not in akme.core
    assert "избыточный контроль процессов" in akme.unload
    assert len(akme.environment) >= 1
    # роль + компенсация в notes обязаны попасть в риски
    assert any("компенсац" in r for r in akme.risk)


def test_akme_vector_survives_empty_synthesis():
    akme = akme_vector_from_synthesis({})

    assert akme.core
    assert akme.unload
    assert akme.environment


def test_akme_reads_structured_output_verbatim():
    """
    Стык контрактов: в state.synthesis лежит именно SynthesisResult.model_dump(),
    и /akme должен читать его без переходников.
    """
    result = SynthesisResult(
        message="связный текст",
        trait_scores={"extraversion": 0.2, "openness": 0.2,
                      "agreeableness": 0.8, "conscientiousness": 0.8,
                      "neuroticism": 0.5},
        core_vs_role={"core": ["самостоятельный анализ"], "role": ["повышенный контроль"]},
        akme_vector={
            "core": ["роли с аналитической ответственностью"],
            "unload": ["избыточный контроль процессов"],
        },
    )

    akme = akme_vector_from_synthesis(result.model_dump())

    assert "роли с аналитической ответственностью" in akme.core
    assert "избыточный контроль процессов" in akme.unload
    # низкая экстраверсия -> тишина; низкая открытость -> конкретика;
    # высокая добросовестность -> риск гиперконтроля
    assert any("тишин" in u for u in akme.unload)
    assert any("конкрет" in c for c in akme.core)
    assert any("контрол" in r for r in akme.risk)


# --- то, ради чего заводилась пятая черта ---

@pytest.mark.parametrize("neuroticism,expected", [
    (0.85, "усталость накапливается"),
    (0.15, "устойчивость под нагрузкой"),
])
def test_neuroticism_drives_the_burnout_block(neuroticism, expected):
    """
    Раньше выгорание можно было упомянуть, только если о нём случайно
    сказали в notes: измерить его было нечем.
    """
    akme = akme_vector_from_synthesis({"trait_scores": {"neuroticism": neuroticism}})

    everything = akme.core + akme.unload + akme.environment + akme.risk
    assert any(expected in line for line in everything)


# --- что видит пользователь ---

def test_user_sees_mbti_only_with_the_disclaimer():
    from app.formatters import format_mbti

    text = format_mbti(mbti_from_traits(TraitScores(
        extraversion=0.2, openness=0.2, agreeableness=0.8, conscientiousness=0.8)))

    assert "ISFJ" in text
    assert "не результат измерения" in text


def test_undecided_mbti_is_not_shown_at_all():
    """Дожимать буквы до какого-нибудь типа нечестно — лучше не показывать."""
    from app.formatters import format_mbti

    assert format_mbti(mbti_from_traits(TraitScores())) == ""


def test_stable_core_traits_are_not_presented_as_strengths():
    """
    Регресс: core_vs_role.core («устойчивое ядро личности») подмешивался в блок,
    подписанный «Опоры (что тебя усиливает)». Человеку с высоким нейротизмом
    система сообщала, что его чувствительность к стрессу — то, что его усиливает.

    На что опираться — это отдельное поле akme_vector.core.
    """
    akme = akme_vector_from_synthesis({
        "trait_scores": {"neuroticism": 0.85, "conscientiousness": 0.85},
        "core_vs_role": {"core": ["чувствительность к стрессу"], "role": ["контроль"]},
        "akme_vector": {"core": ["работа с конкретными задачами"]},
    })

    assert "работа с конкретными задачами" in akme.core
    assert "чувствительность к стрессу" not in akme.core
    # но само наблюдение не теряется: роль по-прежнему уезжает в риски
    assert any("энергозатрат" in r for r in akme.risk)
