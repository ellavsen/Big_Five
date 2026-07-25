import pytest

from core.models import SynthesisResult
from modules.akme_vector import _dominant_letter, akme_vector_from_synthesis


@pytest.mark.parametrize("axis", ["EI", "SN", "TF", "JP"])
def test_axis_polarity_rule_is_the_same_for_all_axes(axis):
    """
    Регресс: EI была инвертирована (1.0 = I), остальные три — нет. LLM применяла
    общее правило и на EI отвечала «наоборот», из-за чего интроверт получал
    рекомендации для экстраверта. Правило должно быть одно: 1.0 = первая буква.
    """
    assert _dominant_letter(axis, 0.9) == axis[0]
    assert _dominant_letter(axis, 0.1) == axis[1]
    assert _dominant_letter(axis, 0.5) == "X"


def test_akme_vector_from_llm_synthesis():
    """На вход идёт результат синтезатора (axis_map / core_vs_role / akme_vector)."""
    synthesis = {
        "message": "связный текст",
        "axis_map": {"EI": 0.8, "SN": 0.2, "TF": 0.7, "JP": 0.9},
        "core_vs_role": {
            "core": ["самостоятельный анализ"],
            "role": ["повышенный контроль"],
        },
        "notes": ["часть контроля выглядит компенсаторной"],
        "akme_vector": {"unload": ["избыточный контроль процессов"]},
    }

    akme = akme_vector_from_synthesis(synthesis)

    assert "самостоятельный анализ" in akme.core
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
    и /akme должен читать его без переходников. Полюса — те же, что в
    prompts/synthesizer.md: 1.0 = первая буква названия оси (E / S / T / J).
    """
    result = SynthesisResult(
        message="связный текст",
        axis_map={"EI": 0.2, "SN": 0.8, "TF": 0.8, "JP": 0.8},
        core_vs_role={"core": ["самостоятельный анализ"], "role": ["повышенный контроль"]},
        akme_vector={"unload": ["избыточный контроль процессов"]},
    )

    akme = akme_vector_from_synthesis(result.model_dump())

    assert "самостоятельный анализ" in akme.core
    assert "избыточный контроль процессов" in akme.unload
    # I → восстановление через тишину; S → конкретика; J → риск гиперконтроля
    assert any("тишин" in u for u in akme.unload)
    assert any("конкрет" in c for c in akme.core)
    assert any("контрол" in r for r in akme.risk)
