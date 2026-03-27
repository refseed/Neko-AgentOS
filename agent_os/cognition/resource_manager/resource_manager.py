from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agent_os.runtime.policies.budget_policy import BudgetPolicy
from agent_os.runtime.state.models import RunState


class ResourceDecision(BaseModel):
    """Output of resource policy for the current step."""

    model_config = ConfigDict(extra="forbid")

    allow_execution: bool
    model_tier: str
    reason: str


class ResourceManager:
    """Owns model tiering and hard budget checks."""

    def __init__(self, budget_policy: BudgetPolicy | None = None) -> None:
        self._budget_policy = budget_policy or BudgetPolicy()

    def decide(self, state: RunState) -> ResourceDecision:
        policy_decision = self._budget_policy.evaluate(state.budget)
        if not policy_decision.allowed:
            return ResourceDecision(
                allow_execution=False,
                model_tier="small",
                reason=policy_decision.reason,
            )
        if state.budget.step_used < 8:
            tier = "small"
        elif state.budget.step_used < 20:
            tier = "medium"
        else:
            tier = "large"
        return ResourceDecision(allow_execution=True, model_tier=tier, reason="ok")
