# core/llm.py
from __future__ import annotations

import logging
import os
from typing import Optional
from openai import AsyncOpenAI
from core.models import TurnPlan, SynthesisResult
from core.utils import extract_json


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
            raw = extract_json(text)
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

    async def synthesize(self, system_prompt: str, user_prompt: str) -> SynthesisResult:
        resp = await self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        text = (resp.output_text or "").strip()
        logger.debug("Synthesis: получен ответ LLM, %d символов", len(text))
        try:
            return SynthesisResult.model_validate(extract_json(text))
        except Exception as e:
            # синтез не должен падать в лицо пользователю, но и молчать об этом нельзя
            logger.warning("Synthesis: не удалось разобрать ответ LLM (%s), отдаём текст как есть", e)
            return SynthesisResult(
                message=text or "Похоже, данных пока мало для связного синтеза.",
                notes=[],
            )
