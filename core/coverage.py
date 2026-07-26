"""Выбор темы следующего хода. Арифметика, а не творчество.

До этого тему выбирала модель: в контекст клали `trait_observations` и надеялись,
что правило со 164-й строки промпта перевесит восемь остальных блоков. Не
перевешивало — планировщик отзеркаливал тему собеседника и уходил в один и тот же
вопрос по кругу.

Здесь тема считается кодом и уходит в промпт приказом, а не подсказкой.

Ритм хода задан тем же кодом: ситуация → максимум одно углубление по детали
рассказа → новая ситуация. Без потолка на углубления получаются семь вопросов
про одно и то же; без углубления вовсе разговор рассыпается на анкету.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.models import ConversationState, Trait
from core.probes import PROBES, PROBES_BY_ID, Probe

# Сколько ходов держимся одной ситуации: ход с вопросом плюс одно углубление.
MAX_TURNS_PER_PROBE = 2


@dataclass(frozen=True)
class TurnGoal:
    """Что делать на этом ходе.

    `opening`   — разговор только начался, ситуацию не подкладываем;
    `follow_up` — углубиться в то, что человек только что рассказал;
    `probe`     — новая ситуация из банка.
    """

    mode: Literal["opening", "follow_up", "probe"]
    probe: Probe | None = None


def trait_observations(state: ConversationState) -> dict[Trait, int]:
    return {t: len(state.evidence.signals_for(t)) for t in Trait}


def _probe_score(probe: Probe, observations: dict[Trait, int]) -> float:
    """Насколько ситуация полезна сейчас.

    Чем меньше собрано по чертам, которые она обычно проявляет, тем выше.
    Убывающая отдача: пятое наблюдение по черте почти ничего не добавляет.
    """
    return sum(1.0 / (1 + observations[t]) for t in probe.traits)


def choose_probe(state: ConversationState) -> Probe | None:
    """Самая полезная из ещё не заданных ситуаций.

    Закрытые черты не исключаем целиком: ситуация обычно проявляет несколько черт
    сразу, и выкидывать её из-за одной закрытой значило бы терять остальные.
    Закрытая черта просто перестаёт добавлять вес.
    """
    used = set(state.used_probes)
    available = [p for p in PROBES if p.id not in used]
    if not available:
        return None

    observations = trait_observations(state)
    # Сортировка по id вторым ключом: при равных весах выбор не должен зависеть
    # от порядка перебора — иначе один и тот же диалог даёт разные ходы.
    return max(available, key=lambda p: (_probe_score(p, observations), p.id))


def plan_turn_goal(state: ConversationState) -> TurnGoal:
    """Решает, что делать на этом ходе: открывать, углублять или менять ситуацию."""
    has_user_speech = any(m.role == "user" for m in state.history)
    if not has_user_speech:
        return TurnGoal(mode="opening")

    current_id = state.used_probes[-1] if state.used_probes else None
    if current_id and state.probe_turns < MAX_TURNS_PER_PROBE:
        return TurnGoal(mode="follow_up", probe=PROBES_BY_ID.get(current_id))

    probe = choose_probe(state)
    if probe is None:
        # Банк исчерпан. Углубляться в последнее сказанное честнее, чем начинать
        # круг по второму разу — именно повторы и были жалобой.
        return TurnGoal(mode="follow_up", probe=PROBES_BY_ID.get(current_id) if current_id else None)

    return TurnGoal(mode="probe", probe=probe)


def register_turn_goal(state: ConversationState, goal: TurnGoal) -> None:
    """Отмечает выданную ситуацию в состоянии, чтобы она больше не повторилась."""
    if goal.mode == "probe" and goal.probe is not None:
        state.used_probes.append(goal.probe.id)
        state.probe_turns = 1
    elif goal.mode == "follow_up":
        state.probe_turns += 1
