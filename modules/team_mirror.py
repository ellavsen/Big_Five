# modules/team_mirror.py
from __future__ import annotations

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

EPISODE_MARKERS = [
    "вчера",
    "сегодня",
    "на прошлой неделе",
    "недавно",
    "однажды",
    "в тот момент",
    "в какой-то момент",
]


def team_mirror(state: ConversationState, text: str) -> None:
    """
    Фиксирует паттерн повторяющейся роли в команде.
    Не интерпретирует личность, а добавляет заметку и слабые сигналы.
    """
    t = (text or "").lower()

    if not any(m in t for m in TEAM_ROLE_MARKERS):
        return

    state.add_note(
        "team_mirror: описана повторяющаяся функция/роль в команде (не разовая ситуация)"
    )

    # direct_example=True ставим только если это конкретный эпизод
    is_episode = any(m in t for m in EPISODE_MARKERS)

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
    if any(x in t for x in ["поддерж", "сглаж", "гармони", "чтобы никому не было плохо"]):
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
