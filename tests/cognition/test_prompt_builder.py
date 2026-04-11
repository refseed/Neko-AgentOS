from __future__ import annotations

from types import SimpleNamespace

from agent_os.cognition.prompt_builder.builder import build_reasoning_prompt, build_reflection_prompt
from agent_os.runtime.state.models import RunState


def test_prompt_builder_handles_optional_fields() -> None:
    state = RunState(run_id="run_1", task_id="task_1", goal="write summary")
    prompt = build_reasoning_prompt(state)
    assert "Goal: write summary" in prompt
    assert "Collected context" in prompt


def test_reflection_prompt_isolated_from_reasoning_prompt() -> None:
    state = RunState(run_id="run_1", task_id="task_1", goal="write summary")
    prompt = build_reflection_prompt(
        state=state,
        draft_text="draft",
        checklist=["Needs evidence"],
    )
    assert "Checklist" in prompt
    assert "Return one of: approved, retry, need_more_evidence." in prompt


def test_prompt_builder_can_use_model_refinement() -> None:
    class FakeGateway:
        def request(self, prompt: str, model_tier: str):
            if "node_mode=reflection" in prompt:
                return SimpleNamespace(
                    text='{"protocol_version":"node-io/v1","node_name":"prompt_builder","confidence":0.9,"notes":[],"prompt":"reflection via model"}'
                )
            return SimpleNamespace(
                text='{"protocol_version":"node-io/v1","node_name":"prompt_builder","confidence":0.9,"notes":[],"prompt":"reasoning via model"}'
            )

    state = RunState(run_id="run_1", task_id="task_1", goal="write summary")
    reasoning_prompt = build_reasoning_prompt(state, model_gateway=FakeGateway(), model_tier="small")
    reflection_prompt = build_reflection_prompt(
        state=state,
        draft_text="draft",
        checklist=["Needs evidence"],
        model_gateway=FakeGateway(),
        model_tier="small",
    )
    assert reasoning_prompt == "reasoning via model"
    assert reflection_prompt == "reflection via model"
