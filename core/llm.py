# core/llm.py
from __future__ import annotations

import logging
import os
from typing import Optional
from openai import AsyncOpenAI
from core.models import TurnPlan, SynthesisResult


logger = logging.getLogger(__name__)


# Сеть: ретраи с экспоненциальным backoff даёт сам SDK, свой цикл не пишем.
LLM_TIMEOUT_SECONDS = 30.0
LLM_MAX_RETRIES = 3

# Ход диалога — короткая живая реплика; синтез — длинный связный текст.
PLAN_MAX_OUTPUT_TOKENS = 800
PLAN_TEMPERATURE = 0.7
SYNTHESIS_MAX_OUTPUT_TOKENS = 2000
SYNTHESIS_TEMPERATURE = 0.4


class AsyncLLMClient:
    """
    Минимальный клиент: один вызов LLM на ход для TurnPlan,
    и отдельный вызов для финального синтеза (когда chosen_agent == synthesizer).

    Форму ответа гарантирует structured outputs (`responses.parse` + strict-схема),
    поэтому ответ не парсится регекспами: либо модель вернула валидный объект,
    либо мы честно уходим в fallback.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.client = AsyncOpenAI(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=LLM_MAX_RETRIES,
        )
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    async def plan_turn(self, system_prompt: str, user_prompt: str) -> TurnPlan:
        try:
            resp = await self.client.responses.parse(
                model=self.model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                text_format=TurnPlan,
                max_output_tokens=PLAN_MAX_OUTPUT_TOKENS,
                temperature=PLAN_TEMPERATURE,
            )
            plan = resp.output_parsed
            if plan is None:
                raise ValueError(f"модель не вернула объект (status={resp.status})")
            return plan

        except Exception as e:
            # 🔒 ЖЁСТКИЙ FALLBACK — СИСТЕМА НЕ ПАДАЕТ.
            # Сюда попадаем на таймауте (после ретраев SDK), отказе модели и обрыве по лимиту.
            logger.warning("TurnPlan: вызов LLM не дал валидный план (%s), уходим в fallback", e)
            return TurnPlan(
                A="ask",
                message="Можем немного замедлиться. Можете привести конкретный пример из недавней ситуации?",
                axis_signals=[],
            )

    async def synthesize(self, system_prompt: str, user_prompt: str) -> SynthesisResult:
        try:
            resp = await self.client.responses.parse(
                model=self.model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                text_format=SynthesisResult,
                max_output_tokens=SYNTHESIS_MAX_OUTPUT_TOKENS,
                temperature=SYNTHESIS_TEMPERATURE,
            )
            result = resp.output_parsed
            if result is None:
                raise ValueError(f"модель не вернула объект (status={resp.status})")
            return result

        except Exception as e:
            # синтез не должен падать в лицо пользователю, но и молчать об этом нельзя
            logger.warning("Synthesis: вызов LLM не дал валидный результат (%s), отдаём мягкую заглушку", e)
            return SynthesisResult(
                message="Похоже, сейчас не получается собрать связный итог. Попробуем ещё раз чуть позже?",
            )
