from core.matching import find_marker, has_episode
from core.models import Axis, AxisSignal, ConversationState

ROLE_MARKERS = ["надо", "должна", "обязана", "контролировать"]
CORE_MARKERS = ["хочется", "мне важно", "я чувствую", "я понимаю"]


def role_vs_core(state: ConversationState, text: str) -> None:
    role = find_marker(text, ROLE_MARKERS)
    core = find_marker(text, CORE_MARKERS)

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
                direct_example=has_episode(text),
            )
        ])
