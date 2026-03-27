from __future__ import annotations

from agent_os.runtime.routing.meta_router import MetaRouter
from agent_os.runtime.state.models import MemoryRefs, RunState


def test_meta_router_returns_structured_routing_decision() -> None:
    router = MetaRouter()
    state = RunState(run_id="run_1", task_id="task_1", goal="demo")
    decision = router.route(state)
    assert decision.next_node in {"blueprint", "reasoning", "investigation", "reflection", "break", "finish"}
    assert isinstance(decision.confidence, float)


def test_meta_router_attaches_memory_mounts() -> None:
    router = MetaRouter()
    state = RunState(
        run_id="run_1",
        task_id="task_1",
        goal="demo",
        memory=MemoryRefs(ram_refs=["ram:1"], cache_refs=["cache:1"], disk_refs=["disk:1"]),
    )
    decision = router.route(state)
    assert isinstance(decision.memory_mounts, list)


def test_meta_router_respects_runtime_allowed_targets() -> None:
    router = MetaRouter()
    state = RunState(run_id="run_1", task_id="task_1", goal="demo")
    decision = router.route(state, allowed_targets={"reflection"})
    assert decision.next_node == "reflection"
