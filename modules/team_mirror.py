# modules/team_mirror.py
from __future__ import annotations

from core.matching import find_marker, has_episode
from core.models import ConversationState, Axis, AxisSignal


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

    # Слабые сигналы как "второй источник" (module), чтобы оси могли закрываться.
    # Очень аккуратно: роль в команде часто коррелирует с J (структура/ответственность)
    # и иногда с F (поддержка/гармония) — но мы даём низкую уверенность.
    signals = []

    # JP: "беру на себя", "организую", "разруливаю" — аккуратный J
    signals.append(
        AxisSignal(
            axis=Axis.JP,
            direction="J",
            confidence=0.25,
            text="паттерн ответственности/организации в командном контексте",
            source="module",
            direct_example=is_episode,
        )
    )

    # TF: если явно про поддержку/гармонизацию
    if find_marker(text, SUPPORT_MARKERS):
        signals.append(
            AxisSignal(
                axis=Axis.TF,
                direction="F",
                confidence=0.25,
                text="фокус на поддержке и гармонизации взаимодействия в команде",
                source="module",
                direct_example=is_episode,
            )
        )

    state.add_signals(signals)
