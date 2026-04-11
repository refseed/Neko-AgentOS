from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_os.cognition.clarification.question_node import ClarificationQuestionError, ClarificationQuestionNode


def test_clarification_question_node_requires_model_gateway() -> None:
    node = ClarificationQuestionNode(node_name="clarification_question")
    with pytest.raises(ClarificationQuestionError):
        node.ask(
            goal="测试目标",
            stage="literature_scan",
            stage_status="need_more_evidence",
            has_source_refs=False,
            context_entry_count=0,
            pending_questions=[],
            draft_preview="",
            interaction_message="",
        )


def test_clarification_question_node_can_use_model_json_output() -> None:
    class FakeGateway:
        def request(self, prompt: str, model_tier: str):
            return SimpleNamespace(
                text=(
                    '{"protocol_version":"node-io/v1","node_name":"clarification_question","confidence":0.82,'
                    '"notes":["from_upstream_intent"],'
                    '"question_for_user":"1. 请确认你最看重的目标（省时间/省钱/省体力）。\\n2. 请说明是否有必须满足的硬条件。",'
                    '"pending_questions":["确认最看重的目标","说明必须满足的硬条件"]}'
                )
            )

    node = ClarificationQuestionNode(node_name="clarification_question", model_gateway=FakeGateway())
    output = node.ask(
        goal="洗车决策",
        stage="literature_scan",
        stage_status="need_more_evidence",
        has_source_refs=False,
        context_entry_count=0,
        pending_questions=["确认最看重的目标", "说明必须满足的硬条件"],
        draft_preview="",
        interaction_message="需要用户参与决策偏好确认",
        model_tier="small",
    )

    assert "1." in output.question_for_user
    assert output.pending_questions == ["确认最看重的目标", "说明必须满足的硬条件"]


def test_clarification_question_node_retries_after_json_parse_failure() -> None:
    class FakeGateway:
        def __init__(self) -> None:
            self.calls = 0

        def request(self, prompt: str, model_tier: str):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(text="not json at all")
            return SimpleNamespace(
                text=(
                    '{"protocol_version":"node-io/v1","node_name":"clarification_question","confidence":0.8,'
                    '"notes":["retry_ok"],'
                    '"question_for_user":"1. 请给出你最在意的评估指标。\\n2. 请给出当前现实约束。",'
                    '"pending_questions":["给出最在意的评估指标","给出当前现实约束"]}'
                )
            )

    gateway = FakeGateway()
    node = ClarificationQuestionNode(
        node_name="clarification_question",
        model_gateway=gateway,
        max_parse_retries=2,
    )
    output = node.ask(
        goal="任务A",
        stage="literature_scan",
        stage_status="need_more_evidence",
        has_source_refs=False,
        context_entry_count=0,
        pending_questions=[],
        draft_preview="",
        interaction_message="",
        model_tier="small",
    )

    assert gateway.calls == 2
    assert output.pending_questions


def test_clarification_question_node_can_generate_from_empty_upstream_intent() -> None:
    class FakeGateway:
        def request(self, prompt: str, model_tier: str):
            return SimpleNamespace(
                text=(
                    '{"protocol_version":"node-io/v1","node_name":"clarification_question","confidence":0.8,'
                    '"notes":["generated_from_context"],'
                    '"question_for_user":"1. 请说明你当前最看重的决策目标。\\n2. 请说明现实约束与硬条件。",'
                    '"pending_questions":["说明最看重的决策目标","说明现实约束与硬条件"]}'
                )
            )

    node = ClarificationQuestionNode(node_name="clarification_question", model_gateway=FakeGateway())
    output = node.ask(
        goal="洗车决策",
        stage="literature_scan",
        stage_status="need_more_evidence",
        has_source_refs=False,
        context_entry_count=0,
        pending_questions=[],
        draft_preview="",
        interaction_message="",
    )
    assert output.pending_questions


def test_clarification_question_node_raises_when_semantics_invalid_after_retries() -> None:
    class FakeGateway:
        def request(self, prompt: str, model_tier: str):
            return SimpleNamespace(
                text=(
                    '{"protocol_version":"node-io/v1","node_name":"clarification_question","confidence":0.8,'
                    '"notes":["bad"],"question_for_user":"请补充更多信息","pending_questions":[]}'
                )
            )

    node = ClarificationQuestionNode(
        node_name="clarification_question",
        model_gateway=FakeGateway(),
        max_parse_retries=1,
    )
    with pytest.raises(ClarificationQuestionError, match="semantic validation failed after 2 attempts"):
        node.ask(
            goal="测试目标",
            stage="literature_scan",
            stage_status="need_more_evidence",
            has_source_refs=False,
            context_entry_count=0,
            pending_questions=[],
            draft_preview="",
            interaction_message="",
            model_tier="small",
        )
