from core.models import Axis, AxisSignal, ConversationState


def role_vs_core(state: ConversationState, text: str) -> None:
    lowered = text.lower()

    role_markers = ["надо", "должна", "обязана", "контролировать"]
    core_markers = ["хочется", "мне важно", "я чувствую", "я понимаю"]

    role = any(w in lowered for w in role_markers)
    core = any(w in lowered for w in core_markers)

    if role and not core:
        state.add_note("role_dominant")

    if core:
        state.add_note("core_expression")

        state.add_signals([
            AxisSignal(
                axis=Axis.TF,
                direction="F",
                confidence=0.3,
                text="выражение чувств и ценностей от первого лица",
                source="module",
                direct_example=True,
            )
        ])
