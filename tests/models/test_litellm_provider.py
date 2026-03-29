from __future__ import annotations

from types import SimpleNamespace

from agent_os.app.config import ModelConfig
from agent_os.models.providers.base import EchoProvider
from agent_os.models.providers.factory import build_model_provider
from agent_os.models.providers.litellm_provider import LiteLLMProvider


def test_litellm_provider_routes_model_by_tier() -> None:
    def fake_completion(**kwargs):
        assert kwargs["model"] == "model-medium"
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok text"))],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
        )

    provider = LiteLLMProvider(
        small_model="model-small",
        medium_model="model-medium",
        large_model="model-large",
        completion_fn=fake_completion,
    )
    response = provider.generate(prompt="hello", model_tier="medium")
    assert response.text == "ok text"
    assert response.input_tokens == 11
    assert response.output_tokens == 7
    assert response.raw["model"] == "model-medium"


def test_litellm_provider_falls_back_on_completion_error() -> None:
    provider = LiteLLMProvider(
        small_model="model-small",
        medium_model="model-medium",
        large_model="model-large",
        completion_fn=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        fallback_provider=EchoProvider(),
    )
    response = provider.generate(prompt="hello", model_tier="small")
    assert isinstance(response.text, str)
    assert response.raw["provider"] == "echo"
    assert response.raw["fallback_from"] == "litellm"
    assert response.raw["litellm_error_type"] == "RuntimeError"


def test_provider_factory_can_select_echo() -> None:
    provider = build_model_provider(ModelConfig(provider="echo"))
    assert isinstance(provider, EchoProvider)


def test_litellm_provider_can_stream_to_console(capsys) -> None:
    def fake_completion(**kwargs):
        assert kwargs["stream"] is True
        assert kwargs["stream_options"]["include_usage"] is True
        chunks = [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="hel"))],
                usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0),
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="lo"))],
                usage=SimpleNamespace(prompt_tokens=9, completion_tokens=2),
            ),
        ]
        return iter(chunks)

    provider = LiteLLMProvider(
        small_model="model-small",
        medium_model="model-medium",
        large_model="model-large",
        stream=True,
        stream_to_console=True,
        completion_fn=fake_completion,
    )
    response = provider.generate(prompt="hello prompt", model_tier="small")
    captured = capsys.readouterr()

    assert response.text == "hello"
    assert response.input_tokens == 9
    assert response.output_tokens == 2
    assert "hello" in captured.out


def test_litellm_provider_retries_non_stream_when_stream_text_is_empty(capsys) -> None:
    calls: list[dict[str, object]] = []

    def fake_completion(**kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("stream") is True:
            chunks = [
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=""))],
                    usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0),
                ),
                SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=""))],
                    usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0),
                ),
            ]
            return iter(chunks)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3),
        )

    provider = LiteLLMProvider(
        small_model="model-small",
        medium_model="model-medium",
        large_model="model-large",
        stream=True,
        stream_to_console=True,
        completion_fn=fake_completion,
    )
    response = provider.generate(prompt="json please", model_tier="small")

    assert response.text == '{"ok":true}'
    assert response.input_tokens == 12
    assert response.output_tokens == 3
    assert len(calls) == 2
    assert calls[0].get("stream") is True
    assert "stream" not in calls[1]

    second = provider.generate(prompt="json please again", model_tier="small")
    assert second.text == '{"ok":true}'
    assert len(calls) == 3
    assert "stream" not in calls[2]
    captured = capsys.readouterr()
    assert '{"ok":true}' in captured.out


def test_litellm_provider_skips_stream_options_for_zai_models() -> None:
    calls: list[dict[str, object]] = []

    def fake_completion(**kwargs):
        calls.append(dict(kwargs))
        if kwargs.get("stream") is True:
            return iter(
                [
                    SimpleNamespace(
                        choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"))],
                        usage=SimpleNamespace(prompt_tokens=6, completion_tokens=1),
                    )
                ]
            )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=6, completion_tokens=1),
        )

    provider = LiteLLMProvider(
        small_model="zai/glm-4.5",
        medium_model="zai/glm-4.7",
        large_model="zai/glm-5",
        stream=True,
        stream_to_console=False,
        completion_fn=fake_completion,
    )
    response = provider.generate(prompt="hello", model_tier="small")

    assert response.text == "ok"
    assert calls
    assert calls[0].get("stream") is True
    assert "stream_options" not in calls[0]


def test_litellm_provider_extracts_json_from_reasoning_content() -> None:
    """Thinking models (e.g. zai/glm-4.5) put output in reasoning_content.
    When content is empty, the provider should extract a valid JSON object from it."""

    reasoning_with_json = (
        "Let me think about this...\n"
        "The user wants JSON output.\n"
        '{"protocol_version": "node-io/v1", "node_name": "test", "confidence": 0.9, '
        '"notes": "ok", "answer": "walk"}\n'
        "Done."
    )

    def fake_completion(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="", reasoning_content=reasoning_with_json),
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=8),
        )

    provider = LiteLLMProvider(
        small_model="model-small",
        medium_model="model-medium",
        large_model="model-large",
        stream=False,
        completion_fn=fake_completion,
    )
    response = provider.generate(prompt="test", model_tier="small")
    import json

    parsed = json.loads(response.text)
    assert parsed["node_name"] == "test"
    assert parsed["answer"] == "walk"


def test_litellm_provider_returns_empty_when_reasoning_has_no_json() -> None:
    """When reasoning_content contains only markdown thinking (no valid JSON),
    the provider should return empty text (triggering retry/error)."""
    from agent_os.models.providers.litellm_provider import EmptyModelResponseError

    truncated_thinking = (
        "1. **Analyze the Request:**\n"
        "   * The user wants to wash their car.\n"
        "   * 100 meters is very short.\n"
        '   * Draft: ```json\n{"protocol_version": "node-io/v1", "question_for_user": [\n```\n'
        "   * (truncated)"
    )

    def fake_completion(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="", reasoning_content=truncated_thinking),
                )
            ],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=8),
        )

    provider = LiteLLMProvider(
        small_model="model-small",
        medium_model="model-medium",
        large_model="model-large",
        stream=False,
        completion_fn=fake_completion,
        empty_text_max_retries=0,
    )

    import pytest

    with pytest.raises(EmptyModelResponseError):
        provider.generate(prompt="test", model_tier="small")


def test_litellm_provider_extracts_reasoning_content_in_stream() -> None:
    """Streaming thinking models emit delta.reasoning_content instead of delta.content."""

    def fake_completion(**kwargs):
        chunks = [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="", reasoning_content="hel"))],
                usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0),
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="", reasoning_content="lo"))],
                usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2),
            ),
        ]
        return iter(chunks)

    provider = LiteLLMProvider(
        small_model="model-small",
        medium_model="model-medium",
        large_model="model-large",
        stream=True,
        stream_to_console=False,
        completion_fn=fake_completion,
    )
    response = provider.generate(prompt="test", model_tier="small")
    assert response.text == "hello"


def test_litellm_provider_retries_then_raises_when_both_content_and_reasoning_empty() -> None:
    """When both content and reasoning_content are empty, retries should happen
    and EmptyModelResponseError must be raised."""
    from agent_os.models.providers.litellm_provider import EmptyModelResponseError

    calls: list[dict[str, object]] = []

    def fake_completion(**kwargs):
        calls.append(dict(kwargs))
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=""))],
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=0),
        )

    provider = LiteLLMProvider(
        small_model="model-small",
        medium_model="model-medium",
        large_model="model-large",
        stream=False,
        completion_fn=fake_completion,
        empty_text_max_retries=2,
    )

    import pytest

    with pytest.raises(EmptyModelResponseError, match="empty text after all retries"):
        provider.generate(prompt="test", model_tier="small")

    assert len(calls) == 3


def test_litellm_provider_succeeds_on_retry_after_empty_text() -> None:
    calls: list[dict[str, object]] = []

    def fake_completion(**kwargs):
        calls.append(dict(kwargs))
        if len(calls) <= 1:
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=""))],
                usage=SimpleNamespace(prompt_tokens=4, completion_tokens=0),
            )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=5),
        )

    provider = LiteLLMProvider(
        small_model="model-small",
        medium_model="model-medium",
        large_model="model-large",
        stream=False,
        completion_fn=fake_completion,
        empty_text_max_retries=2,
    )

    response = provider.generate(prompt="test", model_tier="small")
    assert response.text == '{"ok": true}'
    assert len(calls) == 2
