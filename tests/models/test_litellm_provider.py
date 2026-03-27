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


def test_provider_factory_can_select_echo() -> None:
    provider = build_model_provider(ModelConfig(provider="echo"))
    assert isinstance(provider, EchoProvider)
