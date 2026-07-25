from core.matching import find_marker, has_episode
from core.models import Axis, AxisSignal, ConversationState

DEPLETION_MARKERS = ["устал", "раздраж", "выгор", "нет сил"]
RECOVERY_MARKERS = ["расслаб", "отпуст", "стало легче", "приняла"]


def energy_economy(state: ConversationState, text: str) -> None:
    if find_marker(text, DEPLETION_MARKERS):
        state.add_note("energy:depletion")

    if find_marker(text, RECOVERY_MARKERS):
        state.add_note("energy:recovery")

        state.add_signals([
            AxisSignal(
                axis=Axis.SN,
                direction="S",
                confidence=0.25,
                text="описание телесного облегчения и восстановления энергии",
                # именно "energy", а не "module": на этом источнике держится
                # ветка confidence="high" в modules/synthesizer.py
                source="energy",
                direct_example=has_episode(text),
            )
        ])
