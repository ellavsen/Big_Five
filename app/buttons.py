from telegram import ReplyKeyboardMarkup

BASE_KB = ReplyKeyboardMarkup(
    [
        ["🔁 Сброс", "ℹ️ Помощь"],
    ],
    resize_keyboard=True
)

AFTER_SYNTH_KB = ReplyKeyboardMarkup(
    [
        ["🧭 Практические рекомендации"],
        ["🔁 Сброс", "ℹ️ Помощь"],
    ],
    resize_keyboard=True
)

SYNTH_CONFIRM_KB = ReplyKeyboardMarkup(
    [
        ["✅ Подвести итог"],
        ["↩️ Продолжим разговор"],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)
VOICE_KB = ReplyKeyboardMarkup(
    [["📝 Показать распознанный текст"], ["🔁 Сброс", "ℹ️ Помощь"]],
    resize_keyboard=True
)
