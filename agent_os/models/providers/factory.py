from __future__ import annotations

from agent_os.app.config import ModelConfig
from agent_os.models.providers.base import BaseProvider, EchoProvider
from agent_os.models.providers.litellm_provider import LiteLLMProvider


def build_model_provider(config: ModelConfig) -> BaseProvider:
    """Build provider from file-based config."""

    provider_name = config.provider.lower()
    if provider_name == "echo":
        return EchoProvider()

    mock_response = config.mock_response if config.use_mock else None

    try:
        return LiteLLMProvider(
            small_model=config.small_model,
            medium_model=config.medium_model,
            large_model=config.large_model,
            timeout_sec=config.timeout_sec,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            mock_response=mock_response,
            fallback_provider=EchoProvider(),
        )
    except Exception:
        # Final fallback prevents boot failure when LiteLLM is unavailable.
        return EchoProvider()


def build_model_provider_from_env() -> BaseProvider:
    """Backward-compatible alias now backed by file defaults."""

    return build_model_provider(ModelConfig())
