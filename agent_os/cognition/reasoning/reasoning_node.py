from __future__ import annotations

from typing import Callable, Protocol

from pydantic import BaseModel, ConfigDict

from agent_os.runtime.state.models import RunState


class GatewayResponse(Protocol):
    text: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


class ModelGateway(Protocol):
    def request(self, prompt: str, model_tier: str) -> GatewayResponse:
        ...


class ReasoningResult(BaseModel):
    """Result produced by the reasoning node."""

    model_config = ConfigDict(extra="forbid")

    draft_text: str
    needs_investigation: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0


class ReasoningNode:
    """Build and run one reasoning step."""

    def __init__(self, prompt_builder: Callable[[RunState], str], model_gateway: ModelGateway) -> None:
        self._prompt_builder = prompt_builder
        self._model_gateway = model_gateway

    def run(self, state: RunState) -> ReasoningResult:
        prompt = self._prompt_builder(state)
        response = self._model_gateway.request(prompt=prompt, model_tier=state.routing.model_tier)
        draft_text = response.text
        if not state.payload.accepted_facts:
            return ReasoningResult(
                draft_text=draft_text,
                needs_investigation=True,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                estimated_cost_usd=response.estimated_cost_usd,
            )
        return ReasoningResult(
            draft_text=draft_text,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            estimated_cost_usd=response.estimated_cost_usd,
        )
