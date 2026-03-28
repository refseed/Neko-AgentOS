from __future__ import annotations

from types import SimpleNamespace

from agent_os.app.schemas.requests import StartRunRequest
from agent_os.app.services.orchestrator import AgentOrchestrator
from agent_os.investigation.extract.extractor import DistilledEvidence


class _ClarificationGatewayStub:
    def request(self, prompt: str, model_tier: str):
        if "洗车店离家100米" in prompt:
            return SimpleNamespace(
                text=(
                    '{"protocol_version":"node-io/v1","node_name":"clarification_question","confidence":0.8,'
                    '"notes":["from_upstream_intent"],'
                    '"question_for_user":"1. 你这次决策最看重什么（省时间/省钱/省体力）？\\n2. 两个选项有哪些现实约束？\\n3. 是否有硬条件？",'
                    '"pending_questions":["你最看重什么","两个选项有哪些现实约束","是否有硬条件"]}'
                )
            )
        return SimpleNamespace(
            text=(
                '{"protocol_version":"node-io/v1","node_name":"clarification_question","confidence":0.8,'
                '"notes":["from_upstream_intent"],'
                '"question_for_user":"1. 请说明当前已确认的关键事实。\\n2. 请说明你希望优先满足的约束。",'
                '"pending_questions":["说明关键事实","说明优先约束"]}'
            )
        )


def test_end_to_end_flow_from_start_to_review_result(tmp_path) -> None:
    source_file = tmp_path / "source.txt"
    source_file.write_text(
        "Flow Matching baseline objective uses a transport loss for stable training.",
        encoding="utf-8",
    )
    orchestrator = AgentOrchestrator(workspace_root=tmp_path)
    orchestrator._investigation_runtime_node._clarification_question_node._model_gateway = _ClarificationGatewayStub()  # noqa: SLF001
    result = orchestrator.start_run(
        StartRunRequest(
            goal="read one paper abstract and produce three key points",
            source_paths=[str(source_file)],
        )
    )

    assert result["run_id"].startswith("run_")
    assert result["status"] in {"completed", "paused"}
    assert isinstance(result["verdict"], str)
    assert result["token_used"] > 0
    assert isinstance(result["memory_refs"], dict)


def test_end_to_end_emits_break_report_when_evidence_missing(tmp_path) -> None:
    orchestrator = AgentOrchestrator(workspace_root=tmp_path)
    orchestrator._investigation_runtime_node._clarification_question_node._model_gateway = _ClarificationGatewayStub()  # noqa: SLF001
    orchestrator._investigate = lambda _state: DistilledEvidence(  # noqa: SLF001
        facts=[],
        source_refs=[],
        enough_evidence=False,
    )

    result = orchestrator.start_run(
        StartRunRequest(
            goal="need focused evidence",
            source_paths=[],
        )
    )

    assert result["status"] == "paused"
    assert result["break_report"] is not None
    assert "question_for_user" in result["break_report"]
    question = str(result["break_report"]["question_for_user"])
    assert "关键事实" in question
    assert "1." in question


def test_end_to_end_asks_for_more_sources_when_sources_exist_but_evidence_still_missing(tmp_path) -> None:
    source_file = tmp_path / "source.txt"
    source_file.write_text("placeholder", encoding="utf-8")
    orchestrator = AgentOrchestrator(workspace_root=tmp_path)
    orchestrator._investigation_runtime_node._clarification_question_node._model_gateway = _ClarificationGatewayStub()  # noqa: SLF001
    orchestrator._investigate = lambda _state: DistilledEvidence(  # noqa: SLF001
        facts=[],
        source_refs=[],
        enough_evidence=False,
    )

    result = orchestrator.start_run(
        StartRunRequest(
            goal="need focused evidence",
            source_paths=[str(source_file)],
        )
    )

    assert result["status"] == "paused"
    assert result["break_report"] is not None
    question = str(result["break_report"]["question_for_user"])
    assert "优先满足的约束" in question


def test_end_to_end_debug_mode_includes_routing_steps(tmp_path) -> None:
    orchestrator = AgentOrchestrator(workspace_root=tmp_path)
    orchestrator._investigation_runtime_node._clarification_question_node._model_gateway = _ClarificationGatewayStub()  # noqa: SLF001
    result = orchestrator.start_run(
        StartRunRequest(
            goal="need focused evidence",
            source_paths=[],
        ),
        debug=True,
    )

    assert "debug_steps" in result
    debug_steps = result["debug_steps"]
    assert isinstance(debug_steps, list)
    assert debug_steps
    first_step = debug_steps[0]
    assert first_step["from_node"] == "interaction"
    assert "routing" in first_step


def test_end_to_end_comparison_goal_produces_guided_questions(tmp_path) -> None:
    orchestrator = AgentOrchestrator(workspace_root=tmp_path)
    orchestrator._investigation_runtime_node._clarification_question_node._model_gateway = _ClarificationGatewayStub()  # noqa: SLF001
    orchestrator._investigate = lambda _state: DistilledEvidence(  # noqa: SLF001
        facts=[],
        source_refs=[],
        enough_evidence=False,
    )

    result = orchestrator.start_run(
        StartRunRequest(
            goal="洗车店离家100米，我开车去还是步行去更方便？",
            source_paths=[],
        )
    )

    assert result["status"] == "paused"
    break_report = result["break_report"] or {}
    question = str(break_report.get("question_for_user", ""))
    assert "省时间" in question
    assert "现实约束" in question
