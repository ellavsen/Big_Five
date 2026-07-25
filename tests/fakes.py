from core.models import SynthesisResult, TurnPlan


class FakeLLM:
    """
    Подмена AsyncLLMClient для тестов: тот же публичный API (plan_turn / synthesize),
    но без сети — возвращает заранее заданные объекты.
    """

    def __init__(
        self,
        reply_message: str = "Тестовый вопрос",
        trait_signals: list | None = None,
        synthesis: SynthesisResult | None = None,
    ):
        self.reply_message = reply_message
        self.trait_signals = trait_signals or []
        self.synthesis = synthesis

    async def plan_turn(self, system_prompt: str, user_prompt: str) -> TurnPlan:
        return TurnPlan(
            A="ask",
            message=self.reply_message,
            trait_signals=list(self.trait_signals),
        )

    async def synthesize(self, system_prompt: str, user_prompt: str) -> SynthesisResult:
        return self.synthesis or SynthesisResult(message="Итоговый текст")
