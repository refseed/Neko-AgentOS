from __future__ import annotations

import json
from pathlib import Path
import traceback
from typing import Callable

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


def _execute_with_error_report(action: Callable[[], object]) -> object:
    try:
        return action()
    except Exception as exc:
        error_payload = {
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        typer.echo("执行失败，错误详情如下：", err=True)
        typer.echo(json.dumps(error_payload, ensure_ascii=False), err=True)
        typer.echo(traceback.format_exc(), err=True)
        raise typer.Exit(code=1) from exc


def _print_debug_step(step: dict[str, object]) -> None:
    step_no = step.get("step")
    from_node = step.get("from_node")
    to_node = step.get("to_node")
    status = step.get("status")
    stage = step.get("blueprint_stage")
    stage_status = step.get("stage_status")

    routing = step.get("routing", {})
    if not isinstance(routing, dict):
        routing = {}
    confidence = routing.get("confidence")
    model_tier = routing.get("model_tier")
    candidates = routing.get("candidate_nodes", [])

    capabilities = step.get("capabilities", {})
    if not isinstance(capabilities, dict):
        capabilities = {}
    permission_level = capabilities.get("permission_level", "none")

    budget = step.get("budget", {})
    if not isinstance(budget, dict):
        budget = {}
    step_used = budget.get("step_used")
    max_steps = budget.get("max_steps")
    token_used = budget.get("token_used")

    uncertainty = step.get("uncertainty", {})
    if not isinstance(uncertainty, dict):
        uncertainty = {}
    uncertainty_status = uncertainty.get("status", "none")
    uncertainty_type = uncertainty.get("type")

    typer.echo(
        "[debug] "
        f"step={step_no} {from_node}->{to_node} "
        f"status={status} "
        f"stage={stage}/{stage_status} "
        f"route_conf={confidence} "
        f"tier={model_tier} "
        f"candidates={candidates} "
        f"perm={permission_level} "
        f"uncertainty={uncertainty_status}:{uncertainty_type} "
        f"budget={step_used}/{max_steps} "
        f"tokens={token_used}"
    )
    node_output = step.get("node_output")
    if isinstance(node_output, dict):
        typer.echo(f"[debug:output] {json.dumps(node_output, ensure_ascii=False)}")


def _maybe_resume_paused_run(
    *,
    orchestrator: AgentOrchestrator,
    result: dict[str, object],
    debug: bool,
) -> dict[str, object]:
    latest_result = result
    while latest_result.get("status") == "paused":
        run_id_value = latest_result.get("run_id")
        if not isinstance(run_id_value, str) or not run_id_value.strip():
            break
        run_id = run_id_value.strip()

        break_report = latest_result.get("break_report")
        question = None
        if isinstance(break_report, dict):
            question = break_report.get("question_for_user")

        typer.echo("系统已暂停，等待你补充信息后继续。")
        if isinstance(question, str) and question.strip():
            typer.echo(f"需要补充：\n{question.strip()}")

        if not typer.confirm("现在输入补充信息并继续吗？", default=True):
            typer.echo(f"你可以稍后执行 resume-run，run_id={run_id}")
            break

        user_answer = typer.prompt("请输入补充信息").strip()
        if not user_answer:
            typer.echo("输入为空，无法继续。你可以重新输入，或稍后用 resume-run 继续。")
            continue

        latest_result = _execute_with_error_report(
            lambda: orchestrator.resume_run(
                ResumeRunRequest(run_id=run_id, user_answer=user_answer),
                debug=debug,
                debug_callback=_print_debug_step if debug else None,
            )
        )
        typer.echo(json.dumps(latest_result, ensure_ascii=False))

    return latest_result


@app.command("start-run")
def start_run(
    config: str = typer.Option("config/agent_os.toml", "--config", "-c"),
    debug: bool = typer.Option(False, "--debug", "-d", help="显示路由与运行调试信息"),
) -> None:
    """Interactive start flow."""

    goal = typer.prompt("请输入任务目标").strip()
    source_paths = _prompt_source_paths()
    request = StartRunRequest(goal=goal, source_paths=source_paths)
    debug_callback = _print_debug_step if debug else None
    result = _execute_with_error_report(
        lambda: _build_orchestrator(config).start_run(request, debug=debug, debug_callback=debug_callback)
    )
    typer.echo(json.dumps(result, ensure_ascii=False))


@app.command("resume-run")
def resume_run(
    config: str = typer.Option("config/agent_os.toml", "--config", "-c"),
    debug: bool = typer.Option(False, "--debug", "-d", help="显示路由与运行调试信息"),
) -> None:
    """Interactive resume flow."""

    run_id = typer.prompt("请输入要恢复的 run_id").strip()
    user_answer = typer.prompt("请输入补充信息（可留空）", default="").strip() or None
    request = ResumeRunRequest(run_id=run_id, user_answer=user_answer)
    debug_callback = _print_debug_step if debug else None
    result = _execute_with_error_report(
        lambda: _build_orchestrator(config).resume_run(request, debug=debug, debug_callback=debug_callback)
    )
    typer.echo(json.dumps(result, ensure_ascii=False))


@app.command("run-regression")
def run_regression_command(
    config: str = typer.Option("config/agent_os.toml", "--config", "-c"),
    debug: bool = typer.Option(False, "--debug", "-d", help="显示每个场景的路由调试信息"),
) -> None:
    """Run default regression scenarios locally."""

    orchestrator = _execute_with_error_report(lambda: _build_orchestrator(config))
    scenarios = load_default_scenarios()

    results = _execute_with_error_report(
        lambda: run_regression(
            scenarios=scenarios,
            runner=lambda goal: orchestrator.start_run(
                StartRunRequest(goal=goal, source_paths=[]),
                debug=debug,
                debug_callback=_print_debug_step if debug else None,
            ),
        )
    )
    payload = [
        {"scenario_id": result.scenario_id, "passed": result.passed, "details": result.details}
        for result in results
    ]
    typer.echo(json.dumps(payload, ensure_ascii=False))


@app.command("interactive")
def interactive_console(
    config: str = typer.Option("config/agent_os.toml", "--config", "-c"),
    debug: bool = typer.Option(False, "--debug", "-d", help="交互菜单下显示路由调试信息"),
) -> None:
    """Simple interactive console menu."""

    orchestrator = _execute_with_error_report(lambda: _build_orchestrator(config))
    typer.echo("NekoAgentCore 交互式 CLI")
    while True:
        typer.echo("1) start-run  2) resume-run  3) run-regression  4) exit")
        choice = typer.prompt("请选择操作", default="1").strip()
        if choice == "1":
            try:
                goal = typer.prompt("请输入任务目标").strip()
                source_paths = _prompt_source_paths()
                start_result = _execute_with_error_report(
                    lambda: orchestrator.start_run(
                        StartRunRequest(goal=goal, source_paths=source_paths),
                        debug=debug,
                        debug_callback=_print_debug_step if debug else None,
                    )
                )
                typer.echo(json.dumps(start_result, ensure_ascii=False))
                _maybe_resume_paused_run(orchestrator=orchestrator, result=start_result, debug=debug)
            except typer.Exit:
                typer.echo("start-run 失败，请根据上方错误信息排查后重试。")
        elif choice == "2":
            try:
                run_id = typer.prompt("请输入要恢复的 run_id").strip()
                user_answer = typer.prompt("请输入补充信息（可留空）", default="").strip() or None
                resume_result = _execute_with_error_report(
                    lambda: orchestrator.resume_run(
                        ResumeRunRequest(run_id=run_id, user_answer=user_answer),
                        debug=debug,
                        debug_callback=_print_debug_step if debug else None,
                    )
                )
                typer.echo(json.dumps(resume_result, ensure_ascii=False))
                _maybe_resume_paused_run(orchestrator=orchestrator, result=resume_result, debug=debug)
            except typer.Exit:
                typer.echo("resume-run 失败，请根据上方错误信息排查后重试。")
        elif choice == "3":
            try:
                run_regression_command(config=config, debug=debug)
            except typer.Exit:
                typer.echo("run-regression 失败，请根据上方错误信息排查后重试。")
        elif choice == "4":
            typer.echo("已退出。")
            break
        else:
            typer.echo("无效选择，请重试。")


if __name__ == "__main__":
    app()
