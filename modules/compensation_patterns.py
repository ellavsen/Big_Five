from core.matching import find_marker, has_episode
from core.models import ConversationState, Direction, Trait, TraitSignal

CONTROL_MARKERS = ["контрол", "доказывать", "настаивать", "до конца"]


def compensation_patterns(state: ConversationState, text: str) -> None:
    if not find_marker(text, CONTROL_MARKERS):
        return

    state.add_note("compensation:control")

    state.add_signals([
        TraitSignal(
            trait=Trait.CONSCIENTIOUSNESS,
            direction=Direction.HIGH,
            confidence=0.3,
            text="настойчивость и стремление контролировать процесс",
            source="module",
            # прямой пример — только если описан конкретный случай, а не привычка вообще
            direct_example=has_episode(text),
        )
    ])
