"""Выбор темы хода: банк ситуаций и ритм разговора.

Живой прогон дал семь вопросов подряд про восстановление и пять наблюдений
по одной черте из пяти. Причина была не в модели, а в том, что выбор темы
ей и доверили. Здесь проверяется, что теперь его делает код.
"""
import pytest

from core.coverage import (
    MAX_TURNS_PER_PROBE,
    choose_probe,
    plan_turn_goal,
    register_turn_goal,
)
from core.models import ConversationState, Direction, Trait, TraitSignal
from core.probes import PROBES, PROBES_BY_ID


def make_state(**kw) -> ConversationState:
    state = ConversationState(**kw)
    state.add_user("что-то рассказал")
    return state


def add_signals(state: ConversationState, trait: Trait, count: int) -> None:
    state.add_signals([
        TraitSignal(trait=trait, direction=Direction.HIGH, text=f"наблюдение {i}")
        for i in range(count)
    ])


# --- банк ---------------------------------------------------------------


def test_probe_ids_are_unique():
    assert len({p.id for p in PROBES}) == len(PROBES)


def test_probes_offer_no_answer_options():
    """Вопрос с двумя вариантами — это тест с вариантами ответа.

    Человек выбирает ярлык вместо рассказа, а два полюса в вопросе прямо
    называют измеряемое. Первая версия банка была именно такой.
    """
    with_options = [p.id for p in PROBES if " или " in p.question]
    assert with_options == [], f"вопросы предлагают выбор: {with_options}"


def test_probes_ask_for_a_story():
    """Каждая ситуация должна просить рассказ, а не оценку себя."""
    story_markers = ("расскажи", "вспомни", "когда последний раз", "как прош",
                     "что было", "что осталось", "как она", "как всё", "какая",
                     "что нового", "куда", "есть ")
    weak = [p.id for p in PROBES if not any(m in p.question.lower() for m in story_markers)]
    assert weak == [], f"ситуации не просят рассказа: {weak}"


def test_every_trait_is_covered_by_several_probes():
    for trait in Trait:
        hits = [p.id for p in PROBES if trait in p.traits]
        assert len(hits) >= 3, f"{trait.value} проявляется всего в {len(hits)} ситуациях"


# --- выбор ситуации -----------------------------------------------------


def test_probe_is_never_repeated():
    state = make_state()
    seen = []

    for _ in range(len(PROBES)):
        probe = choose_probe(state)
        assert probe is not None
        assert probe.id not in seen
        seen.append(probe.id)
        state.used_probes.append(probe.id)

    assert choose_probe(state) is None, "банк исчерпан — новых ситуаций быть не должно"


def test_least_covered_traits_win():
    """Ситуация выбирается по тому, чего не хватает, а не по порядку в файле."""
    state = make_state()
    add_signals(state, Trait.NEUROTICISM, 6)
    add_signals(state, Trait.CONSCIENTIOUSNESS, 6)

    probe = choose_probe(state)

    starved = {Trait.OPENNESS, Trait.EXTRAVERSION, Trait.AGREEABLENESS}
    assert starved & set(probe.traits), (
        f"выбрана {probe.id} про {[t.value for t in probe.traits]}, "
        "хотя пустуют другие черты"
    )


def test_choice_is_deterministic():
    """Один и тот же разговор обязан давать один и тот же ход."""
    first = choose_probe(make_state())
    second = choose_probe(make_state())
    assert first.id == second.id


# --- ритм хода ----------------------------------------------------------


def test_conversation_opens_without_a_probe():
    state = ConversationState()
    assert plan_turn_goal(state).mode == "opening"


def test_first_answer_leads_to_a_probe():
    state = make_state()
    assert plan_turn_goal(state).mode == "probe"


def test_one_follow_up_then_a_new_situation():
    """Ритм: ситуация → одно углубление → новая ситуация.

    Без потолка получаются семь вопросов про одно и то же; без углубления
    вовсе разговор превращается в анкету.
    """
    state = make_state()

    first = plan_turn_goal(state)
    register_turn_goal(state, first)
    assert first.mode == "probe"

    second = plan_turn_goal(state)
    register_turn_goal(state, second)
    assert second.mode == "follow_up"
    assert second.probe.id == first.probe.id

    third = plan_turn_goal(state)
    assert third.mode == "probe"
    assert third.probe.id != first.probe.id


def test_follow_up_limit_matches_the_constant():
    state = make_state()
    register_turn_goal(state, plan_turn_goal(state))

    follow_ups = 0
    while plan_turn_goal(state).mode == "follow_up":
        register_turn_goal(state, plan_turn_goal(state))
        follow_ups += 1
        assert follow_ups < 10, "углубление не заканчивается"

    assert follow_ups == MAX_TURNS_PER_PROBE - 1


def test_exhausted_bank_deepens_instead_of_repeating():
    state = make_state()
    state.used_probes.extend(p.id for p in PROBES)
    state.probe_turns = 99

    goal = plan_turn_goal(state)
    assert goal.mode == "follow_up", "повторять круг вопросов нельзя — это и была жалоба"


# --- покрытие на длинном разговоре --------------------------------------


def test_eight_turns_touch_most_of_the_traits():
    """Главный критерий: за восемь ходов разговор не должен упереться в одну черту.

    В живом прогоне до правки было затронуто ровно 1 черта из 5.
    """
    state = make_state()
    touched: set[Trait] = set()

    for _ in range(8):
        goal = plan_turn_goal(state)
        register_turn_goal(state, goal)
        if goal.mode == "probe":
            touched.update(goal.probe.traits)
            # имитируем, что по затронутым чертам что-то собралось
            for trait in goal.probe.traits:
                add_signals(state, trait, 1)

    assert len(touched) >= 4, f"затронуто черт: {len(touched)} — {[t.value for t in touched]}"


@pytest.mark.parametrize("probe_id", [p.id for p in PROBES])
def test_probe_ids_resolve(probe_id):
    assert PROBES_BY_ID[probe_id].question
