from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agent_os.evaluation.scenarios.scenarios import EvaluationScenario


@dataclass(frozen=True)
class RegressionResult:
    scenario_id: str
    passed: bool
    details: str


def run_regression(
    scenarios: list[EvaluationScenario],
    runner: Callable[[str], dict[str, object]],
) -> list[RegressionResult]:
    """Run fixed scenarios against a callable system runner."""

    results: list[RegressionResult] = []
    for scenario in scenarios:
        output = runner(scenario.goal)
        passed = bool(output.get("draft_text")) and bool(output.get("verdict"))
        results.append(
            RegressionResult(
                scenario_id=scenario.scenario_id,
                passed=passed,
                details="ok" if passed else "missing draft or verdict",
            )
        )
    return results
