# core/utils.py
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Any

from core.models import AxisEvidence

from pathlib import Path

import json
import re

def extract_json(text: str) -> dict:
    """
    Безопасно извлекает JSON из ответа LLM.
    Поддерживает:
    - чистый JSON
    - ```json ... ```
    - ``` ... ```
    - JSON внутри произвольного текста
    """
    if not text or not text.strip():
        raise ValueError("Empty LLM response, cannot parse JSON")

    cleaned = text.strip()

    # если markdown-блок
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # до/после JSON может быть текст
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))

def load_text(path: str) -> str:
    """
    Загружает текстовый файл (например, prompt .md) и возвращает его содержимое.
    Путь считается относительным к корню проекта.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    return file_path.read_text(encoding="utf-8")

def serialize_axis_evidence(evidence: AxisEvidence) -> Dict[str, List[Dict[str, Any]]]:
    """
    Компактная нейтральная сериализация evidence для LLM/синтеза.
    """
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for s in evidence.signals:
        out[s.axis.value].append(
            {
                "direction": s.direction,
                "confidence": s.confidence,
                "source": s.source,
                "direct_example": s.direct_example,
                "text": s.text,
            }
        )
    return dict(out)
