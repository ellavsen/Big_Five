from pathlib import Path

import pytest

from core.utils import load_text

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = sorted((ROOT / "prompts").glob("*.md"))

# Где в коде промпты подключаются к оркестратору.
LOADER = ROOT / "app" / "telegram_bot.py"


def test_there_are_prompts_at_all():
    assert PROMPTS, "каталог prompts/ пуст — тест ниже стал бы бессмысленным"


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: p.name)
def test_every_prompt_file_is_actually_loaded(prompt):
    """
    diagnost.md и interpreter.md пролежали в репозитории, не загружаясь никуда,
    и выглядели как мнимая мультиагентность. Ценное из них перенесено
    в turn_planner.md, сами файлы удалены (Этап 3A).
    """
    assert prompt.name in LOADER.read_text(encoding="utf-8"), (
        f"{prompt.name} не загружается — либо подключить, либо удалить, "
        "но не держать мёртвым"
    )


@pytest.mark.parametrize("prompt", PROMPTS, ids=lambda p: p.name)
def test_prompt_is_readable_and_not_empty(prompt):
    assert load_text(f"prompts/{prompt.name}").strip()
