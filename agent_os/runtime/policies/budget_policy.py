from __future__ import annotations

from dataclasses import dataclass

from agent_os.runtime.state.models import BudgetState


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    reason: str


class BudgetPolicy:
    """Simple step/retry circuit breaker policy."""

    def evaluate(self, budget: BudgetState) -> BudgetDecision:
        if budget.step_used >= budget.max_steps:
            return BudgetDecision(allowed=False, reason="max_steps_exceeded")
        if budget.retry_used > budget.max_retries:
            return BudgetDecision(allowed=False, reason="max_retries_exceeded")
        return BudgetDecision(allowed=True, reason="ok")
