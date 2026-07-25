from modules.akme_vector import akme_vector_from_synthesis


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
