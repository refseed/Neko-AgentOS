from __future__ import annotations

from agent_os.app.schemas.requests import ResumeRunRequest
from agent_os.app.services.orchestrator import AgentOrchestrator
from agent_os.runtime.checkpoint.repository import CheckpointRepository
from agent_os.runtime.state.models import BlueprintState, InvestigationState, PayloadState, RunState, UncertaintyState


def test_checkpoint_repository_writes_and_loads_state(tmp_path) -> None:
    repo = CheckpointRepository(db_path=tmp_path / "checkpoints.db", snapshot_dir=tmp_path / "snapshots")
    state = RunState(run_id="run_ckpt", task_id="task_ckpt", goal="checkpoint test")
    checkpoint_id = repo.save(state)

    loaded = repo.load_latest("run_ckpt")
    assert checkpoint_id.startswith("ckpt_")
    assert loaded is not None
    assert loaded.run_id == "run_ckpt"


def test_resume_run_recovers_from_saved_checkpoint(tmp_path) -> None:
    orchestrator = AgentOrchestrator(workspace_root=tmp_path)
    paused_state = RunState(
        run_id="run_resume",
        task_id="task_resume",
        goal="resume task",
        status="paused",
        current_node="break",
        uncertainty=UncertaintyState(
            status="blocked",
            type="user_input_required",
            question_for_user="Need one missing source.",
            blocked_by=["no_source"],
        ),
    )
    orchestrator._checkpoint_repo.save(paused_state)  # noqa: SLF001

    result = orchestrator.resume_run(ResumeRunRequest(run_id="run_resume", user_answer="Use source A"))
    assert result["run_id"] == "run_resume"
    assert result["status"] in {"completed", "paused"}


def test_resume_run_with_user_answer_resets_need_more_evidence_loop(tmp_path) -> None:
    orchestrator = AgentOrchestrator(workspace_root=tmp_path)
    paused_state = RunState(
        run_id="run_resume_loop",
        task_id="task_resume_loop",
        goal="我需要洗车，洗车店离家100米，我是开车去方便？还是步行去方便？",
        status="paused",
        current_node="break",
        payload=PayloadState(stage_result="need_more_evidence"),
        blueprint=BlueprintState(stage_status="need_more_evidence"),
        investigation=InvestigationState(
            active=True,
            pending_questions=[
                "你这次决策最看重什么（省时间、省钱、省体力、舒适度）？",
                "两个选项分别有哪些现实约束？",
            ],
        ),
        uncertainty=UncertaintyState(
            status="blocked",
            type="missing_evidence",
            question_for_user="请补充信息",
            blocked_by=["no_evidence"],
        ),
    )
    orchestrator._checkpoint_repo.save(paused_state)  # noqa: SLF001

    result = orchestrator.resume_run(
        ResumeRunRequest(run_id="run_resume_loop", user_answer="我更看重省时间，洗车店停车方便"),
        debug=True,
    )

    assert result["run_id"] == "run_resume_loop"
    assert any("省时间" in fact for fact in result["accepted_facts"])
    debug_steps = result.get("debug_steps", [])
    strategist_steps = [step for step in debug_steps if step.get("from_node") == "strategist"]
    assert strategist_steps
    first_route = strategist_steps[0]
    assert first_route.get("to_node") == "reasoning"
