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
