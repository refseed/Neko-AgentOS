from __future__ import annotations

from agent_os.app.schemas.requests import StartRunRequest
from agent_os.app.services.orchestrator import AgentOrchestrator
from agent_os.investigation.extract.extractor import DistilledEvidence


def test_end_to_end_flow_from_start_to_review_result(tmp_path) -> None:
    source_file = tmp_path / "source.txt"
    source_file.write_text(
        "Flow Matching baseline objective uses a transport loss for stable training.",
        encoding="utf-8",
    )
    orchestrator = AgentOrchestrator(workspace_root=tmp_path)
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
