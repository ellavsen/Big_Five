from core.models import Axis, AxisSignal, ConversationState


def energy_economy(state: ConversationState, text: str) -> None:
    lowered = text.lower()

    if any(w in lowered for w in ["устал", "раздраж", "выгор", "нет сил"]):
        state.add_note("energy:depletion")

    if any(w in lowered for w in ["расслаб", "отпуст", "стало легче", "приняла"]):
        state.add_note("energy:recovery")

        state.add_signals([
            AxisSignal(
                axis=Axis.SN,
                direction="S",
                confidence=0.25,
                text="описание телесного облегчения и восстановления энергии",
                source="module",
                direct_example=True,
            )
        ])
