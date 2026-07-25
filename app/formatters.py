from typing import List
from modules.akme_vector import AkmeVector

def _bullets(items: List[str]) -> str:
    return "\n".join([f"• {x}" for x in items]) if items else "• (пока пусто)"

def format_akme(akme: AkmeVector) -> str:
    return (
        "🧭 Практические рекомендации (Akme-вектор)\n\n"
        "🌿 Опоры (что тебя усиливает):\n"
        f"{_bullets(akme.core)}\n\n"
        "🔋 Восстановление энергии:\n"
        f"{_bullets(akme.unload)}\n\n"
        "🏡 Среда, в которой будет легче:\n"
        f"{_bullets(akme.environment)}\n\n"
        "⚠️ Риски / где может копиться напряжение:\n"
        f"{_bullets(akme.risk)}"
    )
