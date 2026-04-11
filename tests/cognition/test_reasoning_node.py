from __future__ import annotations

from agent_os.cognition.prompt_builder.builder import build_reasoning_prompt
from agent_os.cognition.reasoning.reasoning_node import ReasoningNode
from agent_os.models.gateway.client import ModelResponse
from agent_os.runtime.state.models import InvestigationState, PayloadState, RunState


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
    assert result.needs_investigation is False
    assert result.input_tokens == 5
    assert result.output_tokens == 7


def test_reasoning_node_no_investigation_without_source_refs() -> None:
    node = ReasoningNode(prompt_builder=build_reasoning_prompt, model_gateway=FakeGateway())
    state = RunState(
        run_id="run_1",
        task_id="task_1",
        goal="simple question",
        payload=PayloadState(source_refs=[]),
    )
    result = node.run(state)
    assert result.needs_investigation is False


def test_reasoning_node_needs_investigation_when_source_refs_exist_but_no_evidence() -> None:
    node = ReasoningNode(prompt_builder=build_reasoning_prompt, model_gateway=FakeGateway())
    state = RunState(
        run_id="run_1",
        task_id="task_1",
        goal="research task",
        payload=PayloadState(source_refs=["data.txt"]),
    )
    result = node.run(state)
    assert result.needs_investigation is True


def test_reasoning_node_skips_investigation_when_evidence_entries_exist() -> None:
    node = ReasoningNode(prompt_builder=build_reasoning_prompt, model_gateway=FakeGateway())
    state = RunState(
        run_id="run_1",
        task_id="task_1",
        goal="reasoning",
        payload=PayloadState(
            source_refs=["data.txt"],
            context_entries=["evidence from investigation"],
        ),
    )
    result = node.run(state)
    assert result.needs_investigation is False


def test_reasoning_node_still_investigates_when_only_user_inputs_with_source_refs() -> None:
    node = ReasoningNode(prompt_builder=build_reasoning_prompt, model_gateway=FakeGateway())
    state = RunState(
        run_id="run_1",
        task_id="task_1",
        goal="reasoning",
        payload=PayloadState(
            source_refs=["data.txt"],
            context_entries=["user_input: 我走路去", "user_input: 车怎么进洗车店"],
        ),
    )
    result = node.run(state)
    assert result.needs_investigation is True


def test_reasoning_node_respects_enough_evidence_even_with_only_user_inputs() -> None:
    node = ReasoningNode(prompt_builder=build_reasoning_prompt, model_gateway=FakeGateway())
    state = RunState(
        run_id="run_1",
        task_id="task_1",
        goal="reasoning",
        payload=PayloadState(
            source_refs=["data.txt"],
            context_entries=["user_input: 我更看重省时间"],
        ),
        investigation=InvestigationState(enough_evidence=True),
    )
    result = node.run(state)
    assert result.needs_investigation is False
