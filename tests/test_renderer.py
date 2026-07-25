from core.renderer import render_profile_with_akme
from modules.akme_vector import AkmeVector


def test_renderer_outputs_text():
    profile = {
        "axes": {},
    }
    akme = AkmeVector(
        core=["test core"],
        unload=[],
        environment=[],
        risk=[]
    )

    text = render_profile_with_akme(profile, akme)
    assert "test core" in text
