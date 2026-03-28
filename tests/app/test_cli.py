from __future__ import annotations

import json

from typer.testing import CliRunner

from agent_os.app import cli as cli_module
from agent_os.app.cli import app

runner = CliRunner()


def _load_json_from_stdout(stdout: str) -> object:
    lines = [line for line in stdout.splitlines() if line.strip()]
    return json.loads(lines[-1])


def test_cli_start_run(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    class FakeOrchestrator:
        def start_run(self, _request, *, debug=False, debug_callback=None):
            return {"run_id": "run_cli_start", "status": "completed"}

    monkeypatch.setattr(cli_module, "_build_orchestrator", lambda _config: FakeOrchestrator())
    result = runner.invoke(app, ["start-run"], input="read one paper\nn\n")
    assert result.exit_code == 0
    payload = _load_json_from_stdout(result.stdout)
    assert payload["run_id"] == "run_cli_start"


def test_cli_resume_run(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    class FakeOrchestrator:
        def resume_run(self, _request, *, debug=False, debug_callback=None):
            return {"run_id": "run_cli_resume", "status": "completed"}

    monkeypatch.setattr(cli_module, "_build_orchestrator", lambda _config: FakeOrchestrator())

    result = runner.invoke(app, ["resume-run"], input="run_cli_resume\nSource provided\n")
    assert result.exit_code == 0
    payload = _load_json_from_stdout(result.stdout)
    assert payload["run_id"] == "run_cli_resume"


def test_cli_run_regression(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    class FakeOrchestrator:
        def start_run(self, _request, *, debug=False, debug_callback=None):
            return {
                "run_id": "run_regression",
                "status": "completed",
                "draft_text": "ok",
                "verdict": "approved",
            }

    monkeypatch.setattr(cli_module, "_build_orchestrator", lambda _config: FakeOrchestrator())
    result = runner.invoke(app, ["run-regression"])
    assert result.exit_code == 0
    payload = _load_json_from_stdout(result.stdout)
    assert isinstance(payload, list)
    assert payload


def test_cli_start_run_prints_error_details_when_orchestrator_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    class FailingOrchestrator:
        def start_run(self, _request, *, debug=False, debug_callback=None):
            raise RuntimeError("boom from orchestrator")

    monkeypatch.setattr(cli_module, "_build_orchestrator", lambda _config: FailingOrchestrator())
    result = runner.invoke(app, ["start-run"], input="read one paper\nn\n")

    assert result.exit_code == 1
    combined_output = f"{result.stdout}\n{getattr(result, 'stderr', '')}"
    assert "RuntimeError" in combined_output
    assert "boom from orchestrator" in combined_output


def test_cli_start_run_debug_prints_routing_steps(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    class FakeOrchestrator:
        def start_run(self, _request, *, debug=False, debug_callback=None):
            if debug and debug_callback is not None:
                debug_callback(
                    {
                        "step": 1,
                        "from_node": "interaction",
                        "to_node": "strategist",
                        "status": "running",
                        "blueprint_stage": "literature_scan",
                        "stage_status": "pending",
                        "routing": {
                            "confidence": 0.9,
                            "model_tier": "small",
                            "candidate_nodes": ["strategist"],
                        },
                        "capabilities": {"permission_level": "readonly"},
                        "budget": {"step_used": 1, "max_steps": 120, "token_used": 12},
                        "uncertainty": {"status": "none", "type": None},
                    }
                )
            return {"run_id": "run_debug", "status": "completed"}

    monkeypatch.setattr(cli_module, "_build_orchestrator", lambda _config: FakeOrchestrator())
    result = runner.invoke(app, ["start-run", "--debug"], input="read one paper\nn\n")

    assert result.exit_code == 0
    assert "[debug] step=1 interaction->strategist" in result.stdout
    payload = _load_json_from_stdout(result.stdout)
    assert payload["run_id"] == "run_debug"
