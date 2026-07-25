# modules/team_mirror.py
from __future__ import annotations

from core.matching import find_marker, has_episode
from core.models import ConversationState, Direction, Trait, TraitSignal


TEAM_ROLE_MARKERS = [
    "ко мне приходят",
    "обычно я",
    "я беру на себя",
    "меня просят",
    "я отвечаю за",
    "часто делаю за других",
    "на мне держится",
    "я закрываю",
    "я тяну",
    "я тащу",
    "я организую",
    "я напоминаю",
    "я разруливаю",
    "я сглаживаю",
    "поддерживаю коллег",
    "помогаю коллегам",
]

SUPPORT_MARKERS = ["поддерж", "сглаж", "гармони", "чтобы никому не было плохо"]


def team_mirror(state: ConversationState, text: str) -> None:
    """
    Фиксирует паттерн повторяющейся роли в команде.
    Не интерпретирует личность, а добавляет заметку и слабые сигналы.
    """
    if not find_marker(text, TEAM_ROLE_MARKERS):
        return

    state.add_note(
        "team_mirror: описана повторяющаяся функция/роль в команде (не разовая ситуация)"
    )

    # direct_example=True ставим только если это конкретный эпизод
    is_episode = has_episode(text)

    # Слабые сигналы как "второй источник" (module), чтобы черты могли закрываться.
    # Очень аккуратно: роль в команде часто коррелирует с добросовестностью
    # (структура/ответственность) и иногда с доброжелательностью (поддержка/гармония) —
    # но мы даём низкую уверенность.
    signals = []

    # "беру на себя", "организую", "разруливаю" — аккуратный сигнал добросовестности
    signals.append(
        TraitSignal(
            trait=Trait.CONSCIENTIOUSNESS,
            direction=Direction.HIGH,
            confidence=0.25,
            text="паттерн ответственности/организации в командном контексте",
            source="module",
            direct_example=is_episode,
        )
    )

    # если явно про поддержку/гармонизацию — доброжелательность
    if find_marker(text, SUPPORT_MARKERS):
        signals.append(
            TraitSignal(
                trait=Trait.AGREEABLENESS,
                direction=Direction.HIGH,
                confidence=0.25,
                text="фокус на поддержке и гармонизации взаимодействия в команде",
                source="module",
                direct_example=is_episode,
            )
        )

    state.add_signals(signals)
