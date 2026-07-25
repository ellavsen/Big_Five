from typing import List

from core.scoring import MbtiReading
from modules.akme_vector import AkmeVector

def _bullets(items: List[str]) -> str:
    return "\n".join([f"• {x}" for x in items]) if items else "• (пока пусто)"


def format_mbti(reading: MbtiReading) -> str:
    """
    Четыре буквы показываем только вместе с оговоркой и только если они собрались.
    Считаются из черт (core/scoring), а не берутся из ответа модели: ядро — Big Five,
    и второй, спорящий с ним источник типа пользователю показывать нечестно.
    """
    if not reading.is_complete:
        return ""

    return (
        f"🔤 Похоже на {reading.letters}\n"
        f"{reading.disclaimer}\n\n"
    )


def format_akme(akme: AkmeVector, mbti: MbtiReading | None = None) -> str:
    return (
        (format_mbti(mbti) if mbti else "")
        + "🧭 Практические рекомендации (Akme-вектор)\n\n"
        "🌿 Опоры (что тебя усиливает):\n"
        f"{_bullets(akme.core)}\n\n"
        # `unload` в промпте — «что разгружать». Раньше подписывалось как
        # «Восстановление энергии», и вывод читался как бессмыслица:
        # «Восстановление энергии: непредсказуемые конфликты».
        "🔋 Что разгрузить, чтобы вернулись силы:\n"
        f"{_bullets(akme.unload)}\n\n"
        "🏡 Среда, в которой будет легче:\n"
        f"{_bullets(akme.environment)}\n\n"
        "⚠️ Риски / где может копиться напряжение:\n"
        f"{_bullets(akme.risk)}"
    )
