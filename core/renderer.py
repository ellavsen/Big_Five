from __future__ import annotations

from modules.akme_vector import AkmeVector

# -------------------------
# Стиль пользователя
# -------------------------

Style = str  # "cautious" | "skeptic" | "tired" | "ambitious" | "formalist" | "neutral"


def infer_style(user_text: str | None, flags: set[str] | None = None) -> Style:
    """
    Детерминированная эвристика:
    1) если есть явный флаг-override — берём его
    2) иначе пытаемся угадать по последнему сообщению
    """
    flags = flags or set()

    # Явные overrides (если ты позже захочешь ставить их модулем/командой)
    if "style_formalist" in flags:
        return "formalist"
    if "style_ambitious" in flags:
        return "ambitious"
    if "style_tired" in flags:
        return "tired"
    if "style_skeptic" in flags:
        return "skeptic"
    if "style_cautious" in flags:
        return "cautious"

    text = (user_text or "").lower().strip()
    if not text:
        return "neutral"

    # Уставший стиль: просьба коротко, усталость, минимум энергии
    tired_markers = ["устал", "устала", "нет сил", "коротко", "быстро", "без подробностей", "в двух словах"]
    if any(m in text for m in tired_markers):
        return "tired"

    # Скептик: сомнение в модели, проверка гипотез, раздражение на типологии
    skeptic_markers = ["не верю", "сомневаюсь", "ерунда", "псевдонаука", "докажи", "проверим", "не уверен(а)"]
    if any(m in text for m in skeptic_markers):
        return "skeptic"

    # Формалист: структура, пункты, чётко, критерии, определения
    formalist_markers = ["структура", "по пунктам", "чётко", "конкретно", "формализовать", "критерии", "схема", "таблица"]
    if any(m in text for m in formalist_markers):
        return "formalist"

    # Амбициозный: рост, эффективность, масштаб, потенциал, «давай дальше»
    ambitious_markers = ["хочу больше", "максимум", "результат", "ускорить", "рост", "потенциал", "карьера", "влияние", "масштаб"]
    if any(m in text for m in ambitious_markers):
        return "ambitious"

    # Осторожный: просит логику, причинно-следственные связи, «поясни ход»
    cautious_markers = ["поясни", "почему", "логика", "как ты понял(а)", "обоснуй", "причинно", "аккуратно"]
    if any(m in text for m in cautious_markers):
        return "cautious"

    return "neutral"

# -------------------------
# Текстовые блоки
# -------------------------

def _intro(style: Style, profile_depth: str, has_comp: bool) -> str:
    if style == "tired":
        return (
            "Собрала краткий профиль и вектор развития. "
            "Без ярлыков — только то, что уже видно по вашим примерам.\n"
        )

    if style == "formalist":
        return (
            "Ниже — итоговый профиль предпочтений и вектор развития.\n"
            "Формат: оси → статус → уверенность → практический вывод.\n"
        )

    if style == "skeptic":
        return (
            "Давайте без магии: это рабочая гипотеза по вашим примерам, а не «ярлык личности». "
            "Где совпадёт — берём, где нет — фиксируем как пограничное.\n"
        )

    if style == "ambitious":
        return (
            "Собрала профиль так, чтобы он работал как инструмент: "
            "где вы сильны естественно, где идёт перегруз, и как усилить влияние без выгорания.\n"
        )

    if style == "cautious":
        return (
            "Я собрала профиль аккуратно: опираюсь на наблюдаемые сигналы, а не на впечатления. "
            "Где данных меньше — отмечаю как пограничное.\n"
        )

    # neutral
    base = (
        "Я аккуратно собрала ваш текущий профиль и возможный вектор развития. "
        "Это не оценка и не диагноз, а описание наблюдаемых предпочтений и зон нагрузки.\n"
    )
    if profile_depth and profile_depth != "базовый":
        base += f"(Глубина профиля: {profile_depth}.)\n"
    if has_comp:
        base += "Отдельно учтены признаки компенсаторного режима — там, где результат достигается ценой энергии.\n"
    return base + "\n"


def _axis_line(style: Style, axis: str, dominant: str, status: str, confidence: str, rationale: str) -> str:
    # tired: короче, без рационализаций
    if style == "tired":
        return f"• {axis}: чаще {dominant} ({status})."

    # formalist: максимально структурно
    if style == "formalist":
        return f"- Ось: {axis} | Предпочтение: {dominant} | Статус: {status} | Уверенность: {confidence}\n  Основание: {rationale}"

    # skeptic: подчёркиваем гипотезу и проверяемость
    if style == "skeptic":
        return f"• {axis}: пока похоже на {dominant} ({status}, {confidence}). Основание: {rationale}"

    # ambitious: фокус на силе/влиянии, но без директив
    if style == "ambitious":
        label = "сильная опора" if status == "core" else ("зона роста" if status == "boundary" else "требует энергии")
        return f"• {axis}: {dominant} ({label}; уверенность: {confidence})."

    # cautious / neutral: ясное объяснение
    return f"• {axis}: чаще {dominant} ({status}, уверенность: {confidence}). Основание: {rationale}"


def _section(style: Style, title: str) -> str:
    if style == "formalist":
        return f"\n{title}:\n"
    if style == "tired":
        return f"\n{title}:\n"
    return f"\n{title}:\n"


def _bullets(style: Style, items: list[str]) -> list[str]:
    if style == "tired":
        # максимум 2 пункта
        items = items[:2]
    if style == "ambitious":
        # оставляем 3, чтобы было динамично
        items = items[:3]
    if style == "formalist":
        return [f"- {i}" for i in items]
    return [f"— {i}" for i in items]


def _closure(style: Style, has_comp: bool) -> str:
    if style == "tired":
        return "\nЕсли хотите, дальше можно уточнить 1–2 места, где уходит больше всего энергии."
    if style == "skeptic":
        return "\nЕсли хотите проверить гипотезу: назовите 1–2 ситуации, где вы действуете противоположно — это быстро прояснит пограничные оси."
    if style == "formalist":
        return "\nПри необходимости следующий шаг — уточнение пограничных осей на 1–2 рабочих примерах."
    if style == "ambitious":
        extra = "особенно" if has_comp else "в первую очередь"
        return f"\nЕсли захотите усилить результат быстрее: {extra} стоит разгрузить компенсаторные зоны — это даст самый большой прирост устойчивости."
    if style == "cautious":
        return "\nЕсли хотите повысить точность, полезно добавить один конкретный пример по самой «тонкой» оси — там, где вы сомневаетесь."
    return "\nЕсли захотите, дальше можно уточнить пограничные оси на паре конкретных примеров — это повысит точность."

# -------------------------
# Главная функция renderer
# -------------------------

def render_profile_with_akme(
    profile: dict,
    akme: AkmeVector,
    user_text: str | None = None,
    flags: set[str] | None = None,
) -> str:
    """
    Детерминированный адаптивный renderer.
    Никакой логики диагностики — только подача результата.
    """
    style = infer_style(user_text, flags=flags)

    axes = profile.get("axes", {})
    profile_depth = profile.get("profile_depth", "базовый")
    has_comp = bool(profile.get("has_compensation", False))

    lines: list[str] = []
    lines.append(_intro(style, profile_depth, has_comp))

    # --- Оси (подача зависит от стиля) ---
    # tired: ограничим до 2–3 осей, чтобы не перегружать
    axis_items = []
    for axis, data in axes.items():
        dominant = data.get("dominant")
        if not dominant:
            continue
        axis_items.append(
            _axis_line(
                style=style,
                axis=axis,
                dominant=dominant,
                status=str(data.get("status", "unknown")),
                confidence=str(data.get("confidence", "low")),
                rationale=str(data.get("rationale", "")),
            )
        )

    if style == "tired":
        axis_items = axis_items[:3]

    if axis_items:
        if style == "formalist":
            lines.append("Профиль по осям:")
            lines.extend(axis_items)
        else:
            lines.append("Профиль по осям:")
            lines.extend(axis_items)

    # --- AKME blocks ---
    if akme.core:
        lines.append(_section(style, "Опора"))
        lines.extend(_bullets(style, akme.core))

    if akme.unload:
        title = "Разгрузка"
        if style == "ambitious":
            title = "Разгрузка (чтобы держать темп)"
        lines.append(_section(style, title))
        lines.extend(_bullets(style, akme.unload))

    if akme.environment:
        lines.append(_section(style, "Поддерживающая среда"))
        lines.extend(_bullets(style, akme.environment))

    if akme.risk:
        title = "Риски при перегрузе"
        if style == "skeptic":
            title = "Риски (проверяемые наблюдением)"
        lines.append(_section(style, title))
        lines.extend(_bullets(style, akme.risk))

        # --- MICRO-INSIGHTS ---
    micro = _micro_insights(profile, style)
    if micro:
        lines.append("\nНебольшие наблюдения для самопроверки:")
        for m in micro:
            if style == "formalist":
                lines.append(f"- {m}")
            else:
                lines.append(f"— {m}")

    # --- Closure ---
    lines.append(_closure(style, has_comp))
    return "\n".join(lines)


# -------------------------
# MICRO-INSIGHTS
# -------------------------

def _micro_insights(profile: dict, style: Style) -> list[str]:
    """
    Короткие зеркала поверх синтеза.
    НЕ диагностика. НЕ советы. НЕ выводы.
    """
    insights: list[str] = []

    axes = profile.get("axes", {})
    has_comp = bool(profile.get("has_compensation", False))

    # 1) Компенсация — главный приоритет
    if has_comp:
        insights.append(
            "Иногда бывает, что человек отлично справляется с задачами, "
            "но ощущение напряжения накапливается — как будто результат держится на усилии. "
            "Это похоже на ваш опыт или скорее нет?"
        )

    # 2) Проходимся по осям
    for axis, data in axes.items():
        status = data.get("status")

        if status == "compensated":
            if axis == "EI":
                insights.append(
                    "Некоторые люди активно взаимодействуют с командой, "
                    "но после этого чувствуют усталость и потребность в тишине. "
                    "У вас это иногда так?"
                )
            elif axis == "JP":
                insights.append(
                    "Бывает, что структура и контроль помогают держать результат, "
                    "но при этом начинают утомлять, если их слишком много. "
                    "Вам это знакомо?"
                )
            elif axis == "TF":
                insights.append(
                    "Иногда учёт эмоций и отношений работает как необходимый навык, "
                    "но требует больше энергии, чем кажется со стороны. "
                    "Это про ваш опыт?"
                )
            elif axis == "SN":
                insights.append(
                    "Бывает, что приходится удерживать фокус не в самом естественном для себя формате — "
                    "и это со временем выматывает. "
                    "Откликается?"
                )

        if status == "boundary":
            insights.append(
                f"По оси {axis} у вас могут по-разному проявляться реакции в зависимости от ситуации. "
                "Бывает, что в одном контексте вы действуете так, а в другом — иначе?"
            )

        # ограничиваем общее число инсайтов
        if len(insights) >= 3:
            break

    # Адаптация под стиль
    if style == "tired":
        return insights[:1]
    if style == "ambitious":
        return insights[:2]
    if style == "formalist":
        # формалисту — только один, максимально нейтральный
        return insights[:1]

    return insights[:3]