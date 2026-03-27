from __future__ import annotations

from agent_os.evaluation.regression.runner import run_regression
from agent_os.evaluation.scenarios.scenarios import load_default_scenarios


def test_regression_runner_executes_default_scenarios() -> None:
    scenarios = load_default_scenarios()
    results = run_regression(
        scenarios=scenarios,
        runner=lambda _goal: {"draft_text": "draft", "verdict": "approved"},
    )
    assert len(results) >= 2
    assert all(result.passed for result in results)
