from __future__ import annotations

from agent_os.cognition.prompt_builder.builder import build_reasoning_prompt
from agent_os.cognition.reasoning.reasoning_node import ReasoningNode
from agent_os.models.gateway.client import ModelResponse
from agent_os.runtime.state.models import PayloadState, RunState


class FakeGateway:
    def request(self, prompt: str, model_tier: str) -> ModelResponse:
        text = f"{model_tier}: {prompt[:30]}"
        return ModelResponse(
            text=text,
            input_tokens=5,
            output_tokens=7,
            estimated_cost_usd=0.0012,
            raw={"provider": "fake"},
        )


def test_reasoning_node_returns_structured_result() -> None:
    node = ReasoningNode(prompt_builder=build_reasoning_prompt, model_gateway=FakeGateway())
    state = RunState(run_id="run_1", task_id="task_1", goal="reasoning")
    result = node.run(state)
    assert isinstance(result.draft_text, str)
    assert result.needs_investigation is True
    assert result.input_tokens == 5
    assert result.output_tokens == 7


def test_reasoning_node_can_skip_investigation_when_facts_exist() -> None:
    node = ReasoningNode(prompt_builder=build_reasoning_prompt, model_gateway=FakeGateway())
    state = RunState(
        run_id="run_1",
        task_id="task_1",
        goal="reasoning",
        payload=PayloadState(accepted_facts=["fact A"]),
    )
    result = node.run(state)
    assert result.needs_investigation is False
