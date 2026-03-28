from __future__ import annotations

from types import SimpleNamespace

from agent_os.cognition.reasoning.reasoning_node import ReasoningResult
from agent_os.cognition.reflection.reflection_node import ReflectionInput, ReflectionNode


def test_reflection_node_approves_grounded_draft() -> None:
    node = ReflectionNode()
    review_input = ReflectionInput(
        stage="idea_summary",
        accepted_facts=["fact"],
        source_refs=["source.txt"],
    )
    verdict = node.review(
        review_input=review_input,
        draft=ReasoningResult(draft_text="Grounded draft with source-backed evidence and clear conclusions."),
    )
    assert verdict.status == "approved"


def test_reflection_node_requests_more_evidence_for_weak_draft() -> None:
    node = ReflectionNode()
    review_input = ReflectionInput(stage="idea_summary")
    verdict = node.review(
        review_input=review_input,
        draft=ReasoningResult(draft_text="Draft", needs_investigation=True),
    )
    assert verdict.status == "need_more_evidence"


def test_reflection_node_can_use_model_verdict() -> None:
    class FakeGateway:
        def request(self, prompt: str, model_tier: str):
            return SimpleNamespace(text='{"status":"approved","issues":[],"next_action":"strategist"}')

    node = ReflectionNode(model_gateway=FakeGateway())
    review_input = ReflectionInput(
        stage="idea_summary",
        accepted_facts=["fact"],
        source_refs=["source.txt"],
    )
    verdict = node.review(
        review_input=review_input,
        draft=ReasoningResult(draft_text="Grounded draft with source-backed evidence and clear conclusions."),
    )
    assert verdict.status == "approved"


def test_reflection_node_build_prompt_is_used_when_gateway_exists() -> None:
    captured: dict[str, str] = {}

    class FakeGateway:
        def request(self, prompt: str, model_tier: str):
            captured["prompt"] = prompt
            return SimpleNamespace(text='{"status":"approved","issues":[],"next_action":"strategist"}')

    node = ReflectionNode(model_gateway=FakeGateway())
    review_input = ReflectionInput(
        stage="idea_summary",
        stage_goal="build summary",
        accepted_facts=["fact"],
        source_refs=["source.txt"],
    )
    node.review(
        review_input=review_input,
        draft=ReasoningResult(draft_text="Grounded draft with source-backed evidence and clear conclusions."),
    )
    assert "stage=idea_summary" in captured["prompt"]


def test_reflection_node_detects_stage_goal_drift() -> None:
    node = ReflectionNode()
    review_input = ReflectionInput(
        stage="idea_summary",
        stage_goal="summarize experimental constraints",
        accepted_facts=["fact"],
        source_refs=["source.txt"],
    )
    verdict = node.review(
        review_input=review_input,
        draft=ReasoningResult(draft_text="This draft discusses writing style but not the requested topic."),
    )
    assert verdict.status == "retry"


def test_reflection_node_is_not_forced_to_need_evidence_when_draft_is_clear() -> None:
    node = ReflectionNode()
    review_input = ReflectionInput(
        stage="idea_summary",
        stage_goal="给出洗车方式建议",
        checklist=["结论明确", "给出可执行建议"],
        accepted_facts=[],
        source_refs=[],
    )
    verdict = node.review(
        review_input=review_input,
        draft=ReasoningResult(
            draft_text="建议直接把车开到洗车店。因为洗车需要车辆在场，步行过去无法完成洗车。",
            needs_investigation=False,
        ),
    )
    assert verdict.status in {"approved", "retry"}
