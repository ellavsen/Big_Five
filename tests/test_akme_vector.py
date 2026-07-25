from modules.akme_vector import akme_vector_from_synthesis


def test_akme_vector_with_compensation():
    profile = {
        "profile_depth": "глубокий",
        "axes": {
            "J/P": {
                "dominant": "J",
                "status": "compensated",
                "confidence": "medium",
                "rationale": "..."
            }
        },
        "has_compensation": True,
        "notes": []
    }

    akme = akme_vector_from_synthesis(profile)

    assert len(akme.unload) >= 1
    assert len(akme.risk) >= 1