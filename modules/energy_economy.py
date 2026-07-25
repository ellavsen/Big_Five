from core.matching import find_marker, has_episode
from core.models import ConversationState, Direction, Trait, TraitSignal

DEPLETION_MARKERS = ["устал", "раздраж", "выгор", "нет сил"]
RECOVERY_MARKERS = ["расслаб", "отпуст", "стало легче", "приняла"]


def energy_economy(state: ConversationState, text: str) -> None:
    """
    Энергия и восстановление — это Neuroticism (реактивность на стресс), а не сенсорика.

    До Этапа 3B черт было четыре, места для этого наблюдения не существовало,
    и «расслабилась, стало легче» уезжало в сигнал Sensing. Теперь истощение
    поднимает neuroticism, восстановление — опускает.
    """
    if find_marker(text, DEPLETION_MARKERS):
        state.add_note("energy:depletion")

        state.add_signals([
            TraitSignal(
                trait=Trait.NEUROTICISM,
                direction=Direction.HIGH,
                confidence=0.3,
                text="описание истощения и нехватки сил",
                source="energy",
                direct_example=has_episode(text),
            )
        ])

    if find_marker(text, RECOVERY_MARKERS):
        state.add_note("energy:recovery")

        state.add_signals([
            TraitSignal(
                trait=Trait.NEUROTICISM,
                direction=Direction.LOW,
                confidence=0.25,
                text="описание телесного облегчения и восстановления энергии",
                source="energy",
                direct_example=has_episode(text),
            )
        ])
