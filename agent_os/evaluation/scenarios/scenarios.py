from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluationScenario:
    scenario_id: str
    goal: str
    expected_checks: list[str]


def load_default_scenarios() -> list[EvaluationScenario]:
    return [
        EvaluationScenario(
            scenario_id="paper_summary",
            goal="read one paper abstract and produce three key points",
            expected_checks=["non-empty draft", "has verdict"],
        ),
        EvaluationScenario(
            scenario_id="compare_methods",
            goal="compare two methods with evidence",
            expected_checks=["non-empty draft", "mentions evidence"],
        ),
    ]
