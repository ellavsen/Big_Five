"""Производные представления профиля.

Ядро оценки — Big Five (OCEAN). Всё в этом модуле выводится из черт и является
интерпретацией, а не измерением. Ничего здесь не должно попадать в сбор сигналов.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.config import (
    TRAIT_FULL_EVIDENCE,
    TRAIT_MAX_DEVIATION,
    TRAIT_MIN_SIGNALS,
)
from core.models import Direction, Trait, TraitEvidence, TraitScores
from core.validity import weigh_trait

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


UNKNOWN = 0.5

# Человеческие названия черт. Живут здесь, потому что нужны и боту, и Mini App:
# два списка разъехались бы при первой же правке формулировки.
TRAIT_TITLES: dict[Trait, str] = {
    Trait.OPENNESS: "открытость опыту",
    Trait.CONSCIENTIOUSNESS: "добросовестность",
    Trait.EXTRAVERSION: "экстраверсия",
    Trait.AGREEABLENESS: "доброжелательность",
    Trait.NEUROTICISM: "реактивность на стресс",
}


def trait_value(trait: Trait, evidence: TraitEvidence) -> float:
    """Выраженность черты 0..1, посчитанная из накопленных наблюдений.

    0.5 означает «данных не хватило», и это не фигура речи: пока наблюдений
    меньше `TRAIT_MIN_SIGNALS`, черта остаётся ровно посередине. Раньше оценку
    ставила модель, и она серединой не пользовалась — одно наблюдение давало 0.70,
    то есть «выражена». Все пять черт выходили высокими: профиль, который приятно
    читать и по которому ничего нельзя решить.

    Считается по перевесу ведущего направления над противоположным: два
    противоречащих друг другу наблюдения оставляют черту у середины, а не
    складываются в уверенность.
    """
    weight = weigh_trait(trait, evidence)

    if weight.direction is None or weight.signals < TRAIT_MIN_SIGNALS:
        return UNKNOWN

    net = max(0.0, weight.score - weight.opposing)
    strength = min(1.0, net / TRAIT_FULL_EVIDENCE)
    shift = TRAIT_MAX_DEVIATION * strength

    value = UNKNOWN + shift if weight.direction is Direction.HIGH else UNKNOWN - shift
    return round(value, 2)


def undetermined_traits(evidence: TraitEvidence) -> list[Trait]:
    """Черты, по которым данных не хватило — те, что остались ровно посередине.

    Нужны, чтобы бот мог честно сказать, насколько полна карта, прежде чем
    предлагать итог. Раньше он обещал «целостную картину» при трёх неизвестных
    чертах из пяти.
    """
    return [t for t in Trait if trait_value(t, evidence) == UNKNOWN]


def trait_scores_from_evidence(evidence: TraitEvidence) -> TraitScores:
    """Все пять черт разом. Единственный источник чисел в профиле."""
    return TraitScores(**{t.value: trait_value(t, evidence) for t in Trait})


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
