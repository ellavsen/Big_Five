import json

class FakeLLM:
    def __init__(self, reply_message="Тестовый вопрос"):
        self.reply_message = reply_message

    async def generate_json(self, system_prompt: str, user_prompt: str) -> str:
        # возвращаем строгий JSON как модель
        return json.dumps({
            "agent_communication": {"G":"ctx3-sig1-val1-map0-sum0","VL":4,"PG":"ctx","AG":"diagnost","R":"test"},
            "A": "ask",
            "message": self.reply_message
        }, ensure_ascii=False)

    async def extract_meaning(self, user_text: str) -> dict:
        # Простой фейковый парсер смысла, достаточный для тестов.
        summary = (user_text or "").strip()
        return {
            "summary": summary,
            "emotions": [],
            "energy_shift": "neutral",
            "implicit_need": "",
            "key_tension": None,
            "self_reflection_level": 0,
            "axis_hints": [],
            "suggested_move": None,
            "content_level": "minimal",
        }
