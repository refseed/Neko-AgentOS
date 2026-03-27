from __future__ import annotations

from agent_os.models.gateway.client import ModelGatewayClient
from agent_os.models.providers.base import BaseProvider, EchoProvider, ProviderResponse


class FakeProvider(BaseProvider):
    def generate(self, prompt: str, model_tier: str) -> ProviderResponse:
        return ProviderResponse(text="fake", input_tokens=3, output_tokens=2, raw={"provider": "fake"})


def test_model_gateway_returns_normalized_response() -> None:
    gateway = ModelGatewayClient(FakeProvider())
    response = gateway.request("hello", "small")
    assert response.text == "fake"
    assert response.input_tokens == 3
    assert response.output_tokens == 2


def test_model_gateway_shape_is_consistent_for_echo_provider() -> None:
    gateway = ModelGatewayClient(EchoProvider())
    response = gateway.request("hello world", "small")
    assert isinstance(response.text, str)
    assert isinstance(response.raw, dict)
