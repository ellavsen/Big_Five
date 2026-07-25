# core/transitions.py
from __future__ import annotations
from core.config import STRICT_VL_THRESHOLD
from core.models import ConversationState

def choose_priority_goal(state: ConversationState) -> str:
    g = state.goals
    # приоритет один
    if g.ctx < 7:
        return "ctx"
    if g.sig < 7:
        return "sig"
    if g.val < 7:
        return "val"
    if g.map < 5:
        return "map"
    return "sum"


def choose_agent(state: ConversationState):
    """
    Управление агентами:
    - diagnost — основной режим
    - interpreter — строго ОДИН раз перед итогом
    - synthesizer — только по подтверждению
    """

    # 🛑 1️⃣ АБСОЛЮТНЫЙ СТОП: диалог зрел
    if state.dialogue_completed:
        if state.synthesis_confirmed:
            return "synthesizer", "Диалог завершён, подводим итог"
        else:
            return "diagnost", "Диалог завершён: итог или смена фокуса"

    # 🛑 2️⃣ ЛОКАЛЬНЫЙ СТОП: карта выполнена
    if state.map_completed:
        if state.synthesis_confirmed:
            return "synthesizer", "Карта завершена, подтверждён синтез"
        else:
            return "diagnost", "Карта собрана: итог или смена фокуса"

    # 🚫 3️⃣ ЗАПРЕТ повторного interpreter
    if state.chosen_agent == "interpreter":
        return "diagnost", "После интерпретации возвращаемся к диалогу"

    # 🧠 4️⃣ ПРЕДЛОЖЕНИЕ ИТОГА (но не синтез)
    if (
        state.validity_level >= STRICT_VL_THRESHOLD
        and state.priority_goal in {"val", "map"}
        and sum(state.trait_closed.values()) >= 2
        and not state.synthesis_confirmed
    ):
        return "diagnost", "Можно предложить подвести итог"

    # 🧩 5️⃣ МЯГКАЯ ИНТЕРПРЕТАЦИЯ — строго один раз
    if (
        state.priority_goal in {"val", "map"}
        and state.validity_level >= STRICT_VL_THRESHOLD - 1
        and sum(state.trait_closed.values()) >= 2
        and not state.interpreter_used
    ):
        return "interpreter", "Мягкая фиксация перед итогом"

    # 🧠 6️⃣ СИНТЕЗ — только по готовности + подтверждению
    if ready_for_synthesis(state) and state.synthesis_confirmed:
        return "synthesizer", "Переход к синтезу"

    # 🔁 7️⃣ ПО УМОЛЧАНИЮ
    return "diagnost", "Продолжаем исследование"


def ready_for_synthesis(state: ConversationState) -> bool:
    soft_closed = sum(1 for v in state.soft_trait_closed.values() if v)
    hard_closed = sum(1 for v in state.trait_closed.values() if v)
    return (
        state.validity_level >= 7
        and soft_closed >= 3
        and hard_closed >= 2
    )

