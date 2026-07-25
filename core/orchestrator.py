# core/orchestrator.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.models import ConversationState, AgentResponse, Axis
from core.llm import AsyncLLMClient
from core.validity import (
    update_validity_from_text,
    axis_is_closed,
    soft_axis_closed,
    is_profile_sufficient,
)
from core.transitions import choose_agent, choose_priority_goal
from core.config import STRICT_MODE, STRICT_VL_THRESHOLD
from core.utils import serialize_axis_evidence
from modules.registry import MODULES
from modules.synthesizer import synthesizer_module


logger = logging.getLogger(__name__)


def _update_axis_closed(state: ConversationState) -> None:
    """Пересчитывает закрытие осей по собранным сигналам."""
    for axis in Axis:
        state.axis_closed[axis] = axis_is_closed(axis, state.evidence)
        state.soft_axis_closed[axis] = soft_axis_closed(axis, state.evidence)


def _update_goals_mvp(state: ConversationState) -> None:
    """
    Обновляет прогресс целей (1..10) грубой эвристикой.
    Важно (2612): эти цели — НЕ «блокиратор» синтеза, а подсказка мета-агенту.
    """

    notes_text = " ".join(state.notes).lower()
    sig_count = len(state.evidence.signals)
    closed_axes = sum(1 for a in Axis if state.axis_closed.get(a))

    # --- ctx ---
    ctx_keys = [
        "работ", "команд", "роль", "должност",
        "ребён", "родител",
        "энерг", "устал", "восстанов", "стресс"
    ]
    if any(k in notes_text for k in ctx_keys):
        state.goals.ctx = max(state.goals.ctx, 5)

    # --- sig ---
    if sig_count >= 2:
        state.goals.sig = max(state.goals.sig, 5)
    if sig_count >= 4:
        state.goals.sig = max(state.goals.sig, 6)
    if sig_count >= 6:
        state.goals.sig = max(state.goals.sig, 7)

    # --- val ---
    if closed_axes >= 1:
        state.goals.val = max(state.goals.val, 5)
    if closed_axes >= 2:
        state.goals.val = max(state.goals.val, 6)
    if closed_axes >= 3:
        state.goals.val = max(state.goals.val, 7)

    # --- map ---
    map_markers = [
        "команд", "совмест", "вместе", "коллег",
        "тим", "лидер", "обратн", "фидбек",
        "конфликт", "обсуждали", "договор",
        "напряжен", "поддерж", "обид", "границ", "коммуникац",
    ]
    map_hits = sum(1 for m in map_markers if m in notes_text)
    if map_hits >= 2:
        state.goals.map = max(state.goals.map, 5)
    if map_hits >= 4:
        state.goals.map = max(state.goals.map, 6)

    # --- sum ---
    # sum — индикатор “созрело ли”, но по 2612 он НЕ должен блокировать синтез.
    if state.validity_level >= 6 and closed_axes >= 2:
        state.goals.sum = max(state.goals.sum, 3)
    if state.validity_level >= STRICT_VL_THRESHOLD and closed_axes >= 3:
        state.goals.sum = max(state.goals.sum, 4)
    if state.validity_level >= STRICT_VL_THRESHOLD + 1 and closed_axes >= 3:
        state.goals.sum = max(state.goals.sum, 5)


class Orchestrator:
    def __init__(
        self,
        llm: AsyncLLMClient,
        turn_planner_prompt: str,
        synthesizer_prompt: str,
    ):
        self.llm = llm
        self.turn_planner_prompt = turn_planner_prompt
        self.synthesizer_prompt = synthesizer_prompt

    def _build_agent_comm(self, state: ConversationState) -> Dict[str, Any]:
        g = state.goals
        g_str = f"ctx{g.ctx}-sig{g.sig}-val{g.val}-map{g.map}-sum{g.sum}"
        return {
            "G": g_str,
            "VL": state.validity_level,
            "PG": state.priority_goal,
            "AG": state.chosen_agent,
            "R": state.reason,
        }

    async def step(self, state: ConversationState, user_text: str) -> AgentResponse:
        """
        Один шаг оркестрации.

        2612-правило:
        - синтез делаем ТОЛЬКО после явного подтверждения (кнопка);
        - когда карта “выразима”, мы прекращаем расспросы и предлагаем итог;
        - STRICT_MODE НЕ запрещает синтез, он только смягчает формулировки.
        """

        user_text = (user_text or "").strip()

        # Если уже завершили и синтез есть — не продолжаем интервью
        if state.dialogue_completed and state.synthesis:
            return AgentResponse(
                agent_communication=self._build_agent_comm(state),
                A="synthesize",
                message="Диагностика уже завершена 🙂 Нажми «🧭 Практические рекомендации», если хочешь прикладной блок.",
            )

        # 1) add user message
        if user_text:
            state.add_user(user_text)

        # 2) run deterministic modules
        for mod in MODULES:
            try:
                mod(state, user_text)
            except Exception as e:
                state.add_note(f"module_error:{getattr(mod, '__name__', str(mod))}:{e}")

        # 3) update validity (heuristic)
        vu = update_validity_from_text(user_text)
        state.clamp_vl(vu.delta)
        state.add_note(f"validity:{vu.note}")

        # 4) recompute axis closed + goals
        _update_axis_closed(state)
        _update_goals_mvp(state)

        # 4.5) readiness (2612): карта стала выразимой
        state.dialogue_saturated = is_profile_sufficient(state)

        # 5) choose PG (оставляем твою механику)
        state.priority_goal = choose_priority_goal(state)
        if state.priority_goal == "map":
            state.map_turns += 1
        else:
            state.map_turns = 0
        if state.map_turns >= 4:
            state.map_completed = True

        # 5.5) Если карта уже выразима, но пользователь НЕ подтвердил итог —
        # больше НЕ задаём новые вопросы: предлагаем “подвести итог”
        if state.dialogue_saturated and not state.synthesis_confirmed and not state.synthesis:
            state.chosen_agent = "diagnost"
            state.reason = "Карта выразима: ожидаем подтверждение итога"
            return AgentResponse(
                agent_communication=self._build_agent_comm(state),
                A="ask",
                message=(
                    "Кажется, у меня уже сложилась целостная картина. "
                    "Хочешь, подведу итог — или продолжим разговор?"
                ),
            )

        # 5.6) Если пользователь подтвердил итог — синтезируем (STRICT_MODE не блокирует)
        if state.synthesis_confirmed and not state.synthesis:
            state.chosen_agent = "synthesizer"
            state.reason = "User confirmed synthesis"

            user_prompt = self._build_synthesis_prompt(state)
            result = await self.llm.synthesize(self.synthesizer_prompt, user_prompt)

            state.add_assistant(result.message)
            # result.message — связный текст для человека, а вся структура уже разобрана
            # в SynthesisResult: axis_map / core_vs_role / akme_vector нужны /akme
            state.synthesis = result.model_dump()

            state.dialogue_completed = True
            state.dialogue_saturated = True
            return AgentResponse(
                agent_communication=self._build_agent_comm(state),
                A="synthesize",
                message=result.message,
            )

        # 6) choose agent for next step (diagnost/interpreter)
        agent, reason = choose_agent(state)

        # Запрет interpreter -> interpreter (одна интерпретация за раз)
        if state.chosen_agent == "interpreter" and agent == "interpreter":
            agent = "diagnost"
            reason = "После интерпретации возвращаемся к сбору сигналов"

        # STRICT_MODE: не запрещает синтез; максимум — ограничивает раннюю интерпретацию
        if STRICT_MODE and agent == "interpreter" and state.validity_level < STRICT_VL_THRESHOLD - 1:
            agent = "diagnost"
            reason = "STRICT_MODE: рано для интерпретации, продолжаем диагностику"

        state.chosen_agent = agent
        state.reason = reason

        # 7) act: один планирующий вызов LLM
        user_prompt = self._build_turn_prompt(state)
        plan = await self.llm.plan_turn(self.turn_planner_prompt, user_prompt)

        if state.chosen_agent == "interpreter":
            plan.A = "interpret"
            state.interpreter_used = True

        # применяем сигналы LLM
        if plan.axis_signals:
            state.add_signals(plan.axis_signals)
            _update_axis_closed(state)

        # сообщение
        state.add_assistant(plan.message)
        logger.debug(
            "VL=%s, AG=%s, PG=%s",
            state.validity_level, state.chosen_agent, state.priority_goal,
        )

        # нормализуем action
        if agent == "diagnost":
            action = "ask"
        elif agent == "interpreter":
            action = "interpret"
            # после интерпретации — выходим в diagnost на следующем ходе
            state.chosen_agent = "diagnost"
        else:
            action = plan.A

        return AgentResponse(
            agent_communication=self._build_agent_comm(state),
            A=action,
            message=plan.message,
        )

    def _build_turn_prompt(self, state: ConversationState) -> str:
        history_for_llm = [{"role": m.role, "content": m.content} for m in state.history[-12:]]
        ev = serialize_axis_evidence(state.evidence)
        g = state.goals

        ctx = {
            "validity_level": state.validity_level,
            "goals": {"ctx": g.ctx, "sig": g.sig, "val": g.val, "map": g.map, "sum": g.sum},
            "priority_goal": state.priority_goal,
            "axis_closed": {k.value: v for k, v in state.axis_closed.items()},
            "soft_axis_closed": {k.value: v for k, v in state.soft_axis_closed.items()},
            "dialogue_saturated": state.dialogue_saturated,
            "notes_tail": state.notes[-8:],
            "evidence_compact": ev,
            "history": history_for_llm,
        }

        return (
            "Сформируй следующий ход живого диалога.\n\n"
            "Контекст состояния (state):\n"
            f"{json.dumps(ctx, ensure_ascii=False)}\n"
        )

    def _build_synthesis_prompt(self, state: ConversationState) -> str:
        ev = serialize_axis_evidence(state.evidence)
        g = state.goals

        # STRICT_MODE = только “тон осторожности”, НЕ запрет
        strict_hint = bool(STRICT_MODE and state.validity_level < STRICT_VL_THRESHOLD)

        # детерминированный разбор осей (ядро / компенсация / пограничность) —
        # считается без LLM и идёт в промпт как опора, а не как готовый вывод
        det_profile = synthesizer_module(state)
        det_profile.pop("notes", None)  # notes передаются отдельным полем ниже

        ctx = {
            "strict_mode": strict_hint,
            "deterministic_profile": det_profile,
            "validity_level": state.validity_level,
            "goals": {"ctx": g.ctx, "sig": g.sig, "val": g.val, "map": g.map, "sum": g.sum},
            "axis_closed": {k.value: v for k, v in state.axis_closed.items()},
            "soft_axis_closed": {k.value: v for k, v in state.soft_axis_closed.items()},
            "notes": state.notes[-20:],
            "evidence_compact": ev,
            "map_completed": state.map_completed,
            "dialogue_saturated": state.dialogue_saturated,
            "history_tail": [m.model_dump() for m in state.history[-12:]],
        }

        return (
            "Собери мягкий синтез. Никаких абсолютов, только вероятности.\n"
            "Если strict_mode=true — будь особенно осторожен: подчёркивай неопределённости и контекст.\n\n"
            f"{json.dumps(ctx, ensure_ascii=False)}\n"
        )
