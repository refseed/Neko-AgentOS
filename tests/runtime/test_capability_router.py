from __future__ import annotations

from agent_os.runtime.routing.capability_router import CapabilityRouter
from agent_os.runtime.state.models import RunState, UncertaintyState


def test_capability_router_returns_readonly_for_investigation() -> None:
    router = CapabilityRouter()
    state = RunState(run_id="run_1", task_id="task_1", goal="demo")
    route = router.route(state=state, next_node="investigation")
    assert route.permission_level == "readonly"


def test_capability_router_blocks_tools_when_uncertainty_blocked() -> None:
    router = CapabilityRouter()
    state = RunState(
        run_id="run_1",
        task_id="task_1",
        goal="demo",
        uncertainty=UncertaintyState(status="blocked", type="user_input_required"),
    )
    route = router.route(state=state, next_node="reasoning")
    assert route.permission_level == "none"
