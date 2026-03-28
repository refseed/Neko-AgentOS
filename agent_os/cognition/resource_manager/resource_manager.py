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
    """Owns hard budget checks and control-plane execution allowance."""

    def __init__(self, budget_policy: BudgetPolicy | None = None, control_model_tier: str = "small") -> None:
        self._budget_policy = budget_policy or BudgetPolicy()
        self._control_model_tier = control_model_tier

    def decide(self, state: RunState) -> ResourceDecision:
        policy_decision = self._budget_policy.evaluate(state.budget)
        if not policy_decision.allowed:
            return ResourceDecision(
                allow_execution=False,
                model_tier=self._control_model_tier,
                reason=policy_decision.reason,
            )
        # Model tier for task execution is decided by Strategist output.
        # Resource manager only selects which tier to run the control-plane call with.
        return ResourceDecision(allow_execution=True, model_tier=self._control_model_tier, reason="ok")
