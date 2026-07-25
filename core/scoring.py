"""Производные представления профиля.

Ядро оценки — Big Five (OCEAN). Всё в этом модуле выводится из черт и является
интерпретацией, а не измерением. Ничего здесь не должно попадать в сбор сигналов.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.models import TraitScores

# Порог, при котором черта считается выраженной. Между порогами — «не определилось»,
# и мы честно показываем X вместо того, чтобы дожимать до буквы.
HIGH = 0.6
LOW = 0.4
UNDECIDED = "X"

# Приблизительное соответствие MBTI ↔ OCEAN. Ровно в таком виде оно записано
# в CLAUDE.md, и ровно так его надо подписывать пользователю: это популярная
# обёртка, а не результат измерения.
#
# У Neuroticism пары в MBTI НЕТ — в четырёхбуквие он не входит вообще.
# Именно поэтому он и не мог собираться, пока черт было четыре.
MBTI_MAPPING = [
    ("extraversion", "E", "I"),        # высокая экстраверсия → E
    ("openness", "N", "S"),            # высокая открытость опыту → N (интуиция)
    ("agreeableness", "F", "T"),       # высокая доброжелательность → F
    ("conscientiousness", "J", "P"),   # высокая добросовестность → J
]

DISCLAIMER = (
    "Четыре буквы — популярная интерпретация поверх Big Five, а не результат "
    "измерения. Соответствие приблизительное, и черта «реактивность на стресс» "
    "в него вообще не входит."
)


@dataclass
class MbtiReading:
    letters: str          # например «ISFJ»; X там, где не определилось
    is_complete: bool     # все четыре буквы определились
    disclaimer: str = DISCLAIMER


def _letter(value: float, high: str, low: str) -> str:
    if value >= HIGH:
        return high
    if value <= LOW:
        return low
    return UNDECIDED


def mbti_from_traits(scores: TraitScores) -> MbtiReading:
    """
    Складывает четыре буквы из четырёх черт. Neuroticism не участвует —
    его нельзя выразить в MBTI, и подменять его чем-то похожим было бы враньём.
    """
    letters = "".join(
        _letter(getattr(scores, trait), high, low)
        for trait, high, low in MBTI_MAPPING
    )
    return MbtiReading(letters=letters, is_complete=UNDECIDED not in letters)
