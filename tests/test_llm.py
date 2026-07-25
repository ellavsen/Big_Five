import pytest
from openai import APITimeoutError
from openai.lib._pydantic import to_strict_json_schema

from core.llm import AsyncLLMClient, LLM_MAX_RETRIES, LLM_TIMEOUT_SECONDS
from core.models import TurnPlan, SynthesisResult


# Ключи в схеме, которые strict-режим structured outputs не принимает.
UNSUPPORTED_KEYWORDS = (
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "minLength", "maxLength", "pattern", "format", "minItems", "maxItems",
)


def _strict_violations(node, path="$") -> list[str]:
    """Обходит схему и собирает всё, на чём API отвергнет strict-запрос."""
    bad = []
    if isinstance(node, dict):
        ap = node.get("additionalProperties")
        if ap is not None and ap is not False:
            # открытый словарь (Dict[str, X]) — самая частая причина отказа
            bad.append(f"{path}.additionalProperties={ap!r}")
        for kw in UNSUPPORTED_KEYWORDS:
            if kw in node:
                bad.append(f"{path}.{kw}={node[kw]!r}")
        for k, v in node.items():
            bad += _strict_violations(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            bad += _strict_violations(v, f"{path}[{i}]")
    return bad


@pytest.mark.parametrize("model", [TurnPlan, SynthesisResult])
def test_schema_is_strict_compatible(model):
    """
    Контракт этапа 2A: обе модели уходят в API как strict-схемы.
    Локальный хелпер SDK такие нарушения пропускает молча — отказ приходит
    только от API, поэтому проверяем схему сами.
    """
    assert _strict_violations(to_strict_json_schema(model)) == []


def test_all_fields_required_in_schema():
    """Strict требует, чтобы модель заполнила все поля, даже те, у которых есть default."""
    schema = to_strict_json_schema(SynthesisResult)
    assert set(schema["required"]) == set(schema["properties"])


class _FailingResponses:
    """Подмена client.responses: воспроизводит отказ вместо сетевого вызова."""

    def __init__(self, exc=None, parsed=None, status="completed"):
        self.exc = exc
        self.parsed = parsed
        self.status = status
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return type("Resp", (), {"output_parsed": self.parsed, "status": self.status})()


def _client_with(responses) -> AsyncLLMClient:
    client = AsyncLLMClient(api_key="test-key")
    client.client.responses = responses
    return client


def test_client_sets_timeout_and_retries():
    """Backoff берём у SDK, но лимиты должны быть выставлены явно."""
    llm = AsyncLLMClient(api_key="test-key")
    assert llm.client.timeout == LLM_TIMEOUT_SECONDS
    assert llm.client.max_retries == LLM_MAX_RETRIES
    assert LLM_MAX_RETRIES >= 1


@pytest.mark.asyncio
async def test_plan_turn_falls_back_on_timeout():
    """Таймаут (уже после ретраев SDK) не должен ронять ход диалога."""
    fake = _FailingResponses(exc=APITimeoutError(request=None))
    plan = await _client_with(fake).plan_turn("system", "user")

    assert isinstance(plan, TurnPlan)
    assert plan.A == "ask"
    assert plan.message
    assert plan.trait_signals == []


@pytest.mark.asyncio
async def test_synthesize_falls_back_on_timeout():
    fake = _FailingResponses(exc=APITimeoutError(request=None))
    result = await _client_with(fake).synthesize("system", "user")

    assert isinstance(result, SynthesisResult)
    assert result.message
    assert result.akme_vector is None


@pytest.mark.asyncio
async def test_plan_turn_falls_back_when_model_returns_nothing():
    """Отказ модели или обрыв по max_output_tokens → output_parsed = None."""
    fake = _FailingResponses(parsed=None, status="incomplete")
    plan = await _client_with(fake).plan_turn("system", "user")

    assert plan.A == "ask"


@pytest.mark.asyncio
async def test_plan_turn_requests_structured_output():
    """Форму ответа задаём схемой, а не просьбой в промпте."""
    fake = _FailingResponses(parsed=TurnPlan(A="ask", message="ок"))
    await _client_with(fake).plan_turn("system", "user")

    kwargs = fake.calls[0]
    assert kwargs["text_format"] is TurnPlan
    assert kwargs["max_output_tokens"] > 0
    assert "temperature" in kwargs
