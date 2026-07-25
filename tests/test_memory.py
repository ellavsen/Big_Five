import json
from datetime import datetime, timezone

import pytest

import app.telegram_bot as bot
from core.models import ConversationState, PreviousProfile, SynthesisResult, TraitScores
from core.orchestrator import Orchestrator
from tests.fakes import FakeLLM

FINISHED_AT = datetime(2026, 3, 14, 9, 30, tzinfo=timezone.utc)


def _last_synthesis() -> dict:
    """То, что реально лежит в synthesis.raw_json — SynthesisResult.model_dump()."""
    return SynthesisResult(
        message="прошлый тёплый текст",
        trait_scores=TraitScores(conscientiousness=0.85, neuroticism=0.7, extraversion=0.2),
        notes=["часть контроля выглядит компенсаторной", "восстанавливается в одиночестве"],
    ).model_dump(mode="json")


def test_previous_profile_is_built_from_db_row():
    profile = bot._previous_profile_from_row((FINISHED_AT, _last_synthesis()))

    assert profile.finished_at == "2026-03-14"
    assert profile.trait_scores.conscientiousness == 0.85
    assert profile.trait_scores.neuroticism == 0.7
    assert "часть контроля выглядит компенсаторной" in profile.notes


def test_first_conversation_has_no_memory():
    assert bot._previous_profile_from_row(None) is None


def test_profile_keeps_traits_but_not_the_whole_previous_text():
    """
    В память кладём черты и заметки, но не прошлый итог целиком: он длинный
    и уводит модель в пересказ вместо наблюдения.
    """
    profile = bot._previous_profile_from_row((FINISHED_AT, _last_synthesis()))

    assert "прошлый тёплый текст" not in json.dumps(profile.model_dump(), ensure_ascii=False)


def test_notes_are_capped():
    raw = _last_synthesis()
    raw["notes"] = [f"заметка {i}" for i in range(20)]

    assert len(bot._previous_profile_from_row((FINISHED_AT, raw)).notes) == 5


def test_incompatible_old_profile_does_not_break_the_dialogue():
    """Прошлый итог мог сохраниться другой версией контракта — тогда просто нет памяти."""
    assert bot._previous_profile_from_row((FINISHED_AT, {"trait_scores": "мусор"})) is None
    assert bot._previous_profile_from_row((FINISHED_AT, None)) is None


@pytest.mark.asyncio
async def test_previous_profile_reaches_both_prompts():
    orch = Orchestrator(FakeLLM(), turn_planner_prompt="TURN", synthesizer_prompt="SYNTH")

    state = ConversationState()
    state.previous_profile = PreviousProfile(
        finished_at="2026-03-14",
        trait_scores=TraitScores(neuroticism=0.7),
        notes=["восстанавливается в одиночестве"],
    )

    for prompt in (orch._build_turn_prompt(state), orch._build_synthesis_prompt(state)):
        ctx = json.loads(prompt.split("\n", 1)[1].strip().splitlines()[-1])
        assert ctx["previous_profile"]["finished_at"] == "2026-03-14"
        assert ctx["previous_profile"]["trait_scores"]["neuroticism"] == 0.7


@pytest.mark.asyncio
async def test_prompts_say_it_is_a_first_conversation_when_there_is_no_memory():
    orch = Orchestrator(FakeLLM(), turn_planner_prompt="TURN", synthesizer_prompt="SYNTH")

    ctx = json.loads(
        orch._build_turn_prompt(ConversationState()).split("\n", 1)[1].strip().splitlines()[-1]
    )
    assert ctx["previous_profile"] is None


def test_memory_survives_the_state_snapshot():
    """Память едет в sessions.state_json вместе с остальным состоянием."""
    state = ConversationState()
    state.previous_profile = PreviousProfile(
        finished_at="2026-03-14", trait_scores=TraitScores(neuroticism=0.7)
    )

    restored = ConversationState.model_validate(json.loads(json.dumps(state.model_dump(mode="json"))))

    assert restored.previous_profile.trait_scores.neuroticism == 0.7
