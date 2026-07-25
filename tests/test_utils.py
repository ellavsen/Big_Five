import pytest

from core.utils import extract_json


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_markdown_fence():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_inside_text():
    """LLM иногда пишет пояснение до/после JSON."""
    assert extract_json('Вот результат:\n{"a": 1}\nготово') == {"a": 1}


def test_extract_json_empty_raises():
    with pytest.raises(ValueError):
        extract_json("   ")
