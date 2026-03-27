from __future__ import annotations

from agent_os.cognition.memory_router.memory_router import MemoryRouter
from agent_os.cognition.resource_manager.resource_manager import ResourceManager
from agent_os.cognition.strategist.strategist import RoutingDecision, Strategist
from agent_os.runtime.state.models import RunState


class MetaRouter:
    """Facade that combines strategist, budget, and memory routing."""

    def __init__(
        self,
        strategist: Strategist | None = None,
        resource_manager: ResourceManager | None = None,
        memory_router: MemoryRouter | None = None,
    ) -> None:
        self._strategist = strategist or Strategist()
        self._resource_manager = resource_manager or ResourceManager()
        self._memory_router = memory_router or MemoryRouter()

    def route(self, state: RunState, allowed_targets: set[str] | None = None) -> RoutingDecision:
        resource_decision = self._resource_manager.decide(state)
        decision = self._strategist.decide(state, resource_decision, allowed_targets=allowed_targets)
        mounts = self._memory_router.plan_mounts(state, decision.next_node)
        return decision.model_copy(update={"memory_mounts": mounts})
