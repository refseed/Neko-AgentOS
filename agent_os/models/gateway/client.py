from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from agent_os.models.pricing.rules import estimate_cost_usd
from agent_os.models.providers.base import BaseProvider


class ModelResponse(BaseModel):
    """Normalized model output used by the rest of the system."""

    model_config = ConfigDict(extra="forbid")

    text: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    raw: dict[str, object] = Field(default_factory=dict)


class ModelGatewayClient:
    """Provider-agnostic model gateway."""

    def __init__(self, provider: BaseProvider) -> None:
        self._provider = provider

    def request(self, prompt: str, model_tier: str) -> ModelResponse:
        provider_response = self._provider.generate(prompt=prompt, model_tier=model_tier)
        return ModelResponse(
            text=provider_response.text,
            input_tokens=provider_response.input_tokens,
            output_tokens=provider_response.output_tokens,
            estimated_cost_usd=estimate_cost_usd(
                model_tier=model_tier,
                input_tokens=provider_response.input_tokens,
                output_tokens=provider_response.output_tokens,
            ),
            raw=provider_response.raw,
        )

    def generate(self, prompt: str, model_tier: str) -> str:
        """Compatibility helper for cognition nodes that only need text."""

        return self.request(prompt=prompt, model_tier=model_tier).text
