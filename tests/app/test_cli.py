from __future__ import annotations

import json

from typer.testing import CliRunner

from agent_os.app.cli import app
from agent_os.app.services.orchestrator import AgentOrchestrator
from agent_os.runtime.state.models import RunState, UncertaintyState

runner = CliRunner()


def _load_json_from_stdout(stdout: str) -> object:
    lines = [line for line in stdout.splitlines() if line.strip()]
    return json.loads(lines[-1])


def test_cli_start_run(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["start-run"], input="read one paper\nn\n")
    assert result.exit_code == 0
    payload = _load_json_from_stdout(result.stdout)
    assert payload["run_id"].startswith("run_")


def test_cli_resume_run(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    orchestrator = AgentOrchestrator(workspace_root=tmp_path)
    paused_state = RunState(
        run_id="run_cli_resume",
        task_id="task_cli_resume",
        goal="resume goal",
        status="paused",
        current_node="break",
        uncertainty=UncertaintyState(
            status="blocked",
            type="user_input_required",
            question_for_user="Need one source",
            blocked_by=["missing_input"],
        ),
    )
    orchestrator._checkpoint_repo.save(paused_state)  # noqa: SLF001

    result = runner.invoke(app, ["resume-run"], input="run_cli_resume\nSource provided\n")
    assert result.exit_code == 0
    payload = _load_json_from_stdout(result.stdout)
    assert payload["run_id"] == "run_cli_resume"


def test_cli_run_regression(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["run-regression"])
    assert result.exit_code == 0
    payload = _load_json_from_stdout(result.stdout)
    assert isinstance(payload, list)
    assert payload
