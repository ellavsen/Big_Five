from core.models import Axis, AxisSignal, ConversationState


def compensation_patterns(state: ConversationState, text: str) -> None:
    lowered = text.lower()

    if any(w in lowered for w in ["контрол", "доказывать", "настаивать", "до конца"]):
        state.add_note("compensation:control")

        state.add_signals([
            AxisSignal(
                axis=Axis.JP,
                direction="J",
                confidence=0.3,
                text="настойчивость и стремление контролировать процесс",
                source="module",
                direct_example=True,
            )
        ])
