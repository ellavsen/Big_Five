# core/llm.py
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional
from openai import AsyncOpenAI
import re
from core.models import TurnPlan, SynthesisResult


logger = logging.getLogger(__name__)


class AsyncLLMClient:
    """
    Минимальный клиент: один вызов LLM на ход для TurnPlan,
    и отдельный вызов для финального синтеза (когда chosen_agent == synthesizer).
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def _normalize_turnplan_payload(self, data: dict) -> dict:
        """
        Приводит старые/ошибочные форматы LLM к новому контракту TurnPlan.
        """
    # старый формат → новый
        if "A" not in data:
            if "suggested_move" in data:
                data["A"] = data["suggested_move"]
            elif "reaction" in data:
                data["A"] = "interpret"
            else:
                data["A"] = "ask"

        if "message" not in data:
            if "reaction" in data:
                data["message"] = data["reaction"]
            else:
                data["message"] = "Продолжим."

        if "axis_signals" not in data:
            data["axis_signals"] = []

        return data

    async def plan_turn(self, system_prompt: str, user_prompt: str) -> TurnPlan:
        resp = await self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        text = (resp.output_text or "").strip()
        logger.debug("TurnPlan: получен ответ LLM, %d символов", len(text))
        try:
            raw = self._safe_extract_json(text)
            normalized = self._normalize_turnplan_payload(raw)
            return TurnPlan.model_validate(normalized)

        except Exception as e:
        # 🔒 ЖЁСТКИЙ FALLBACK — СИСТЕМА НЕ ПАДАЕТ
            logger.warning("TurnPlan: не удалось разобрать ответ LLM (%s), уходим в fallback", e)
            return TurnPlan(
                A="ask",
                message="Можем немного замедлиться. Можете привести конкретный пример из недавней ситуации?",
                axis_signals=[],
            )

    def _safe_extract_json(self, text: str) -> dict:
        """
        Пытается извлечь JSON из ответа LLM.
        Работает даже если до/после есть текст.
        """
        if not text or not text.strip():
            raise ValueError("LLM returned empty response")

        text = text.strip()

    # 1) если это уже чистый JSON
        if text.startswith("{") and text.endswith("}"):
            return json.loads(text)

    # 2) пробуем вытащить JSON из текста
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))

        raise ValueError("No JSON object found in LLM response")
    
    async def synthesize(self, system_prompt: str, user_prompt: str) -> SynthesisResult:
        resp = await self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = resp.output_text.strip()
        try:
            data = json.loads(text)
        except Exception:
            data = {"message": text or "Похоже, данных пока мало для связного синтеза.", "notes": []}
        return SynthesisResult.model_validate(data)
