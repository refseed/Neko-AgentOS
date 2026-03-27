from __future__ import annotations

from agent_os.app.schemas.requests import ResumeRunRequest
from agent_os.app.services.orchestrator import AgentOrchestrator
from agent_os.runtime.checkpoint.repository import CheckpointRepository
from agent_os.runtime.state.models import RunState, UncertaintyState


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
