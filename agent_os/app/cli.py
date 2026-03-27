from __future__ import annotations

import json
from pathlib import Path

import typer

from agent_os.app.schemas.requests import ResumeRunRequest, StartRunRequest
from agent_os.app.services.orchestrator import AgentOrchestrator
from agent_os.evaluation.regression.runner import run_regression
from agent_os.evaluation.scenarios.scenarios import load_default_scenarios

app = typer.Typer(help="NekoAgentCore Agent OS CLI")


def _build_orchestrator(config_path: str | None = None) -> AgentOrchestrator:
    path = Path(config_path) if config_path else None
    return AgentOrchestrator(workspace_root=Path.cwd(), config_path=path)


def _prompt_source_paths() -> list[str]:
    paths: list[str] = []
    while typer.confirm("是否添加一个来源文件路径？", default=False):
        raw = typer.prompt("请输入来源文件路径").strip()
        if raw:
            paths.append(raw)
    return paths


@app.command("start-run")
def start_run(config: str = typer.Option("config/agent_os.toml", "--config", "-c")) -> None:
    """Interactive start flow."""

    goal = typer.prompt("请输入任务目标").strip()
    source_paths = _prompt_source_paths()
    request = StartRunRequest(goal=goal, source_paths=source_paths)
    result = _build_orchestrator(config).start_run(request)
    typer.echo(json.dumps(result, ensure_ascii=False))


@app.command("resume-run")
def resume_run(config: str = typer.Option("config/agent_os.toml", "--config", "-c")) -> None:
    """Interactive resume flow."""

    run_id = typer.prompt("请输入要恢复的 run_id").strip()
    user_answer = typer.prompt("请输入补充信息（可留空）", default="").strip() or None
    request = ResumeRunRequest(run_id=run_id, user_answer=user_answer)
    result = _build_orchestrator(config).resume_run(request)
    typer.echo(json.dumps(result, ensure_ascii=False))


@app.command("run-regression")
def run_regression_command(config: str = typer.Option("config/agent_os.toml", "--config", "-c")) -> None:
    """Run default regression scenarios locally."""

    orchestrator = _build_orchestrator(config)
    scenarios = load_default_scenarios()

    results = run_regression(
        scenarios=scenarios,
        runner=lambda goal: orchestrator.start_run(StartRunRequest(goal=goal, source_paths=[])),
    )
    payload = [
        {"scenario_id": result.scenario_id, "passed": result.passed, "details": result.details}
        for result in results
    ]
    typer.echo(json.dumps(payload, ensure_ascii=False))


@app.command("interactive")
def interactive_console(config: str = typer.Option("config/agent_os.toml", "--config", "-c")) -> None:
    """Simple interactive console menu."""

    typer.echo("NekoAgentCore 交互式 CLI")
    while True:
        typer.echo("1) start-run  2) resume-run  3) run-regression  4) exit")
        choice = typer.prompt("请选择操作", default="1").strip()
        if choice == "1":
            start_run(config)
        elif choice == "2":
            resume_run(config)
        elif choice == "3":
            run_regression_command(config)
        elif choice == "4":
            typer.echo("已退出。")
            break
        else:
            typer.echo("无效选择，请重试。")


if __name__ == "__main__":
    app()
