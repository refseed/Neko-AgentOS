from __future__ import annotations

import pytest

from agent_os.runtime.graph.engine import GraphEngine, IllegalEdgeError, NodeResult
from agent_os.runtime.state.models import RunState


def test_graph_engine_runs_legal_edge_without_mutating_original_state() -> None:
    state = RunState(run_id="run_demo", task_id="task_demo", goal="demo goal")
    engine = GraphEngine(
        handlers={"interaction": lambda _state: NodeResult(next_node="finish", state_delta={"status": "running"})},
        legal_edges={"interaction": {"finish"}},
    )

    next_state = engine.run_one_step(state)

    assert state.current_node == "interaction"
    assert next_state.current_node == "finish"
    assert next_state.budget.step_used == 1


def test_graph_engine_blocks_illegal_edge() -> None:
    state = RunState(run_id="run_demo", task_id="task_demo", goal="demo goal")
    engine = GraphEngine(
        handlers={"interaction": lambda _state: NodeResult(next_node="finish", state_delta={})},
        legal_edges={"interaction": {"strategist"}},
    )

    with pytest.raises(IllegalEdgeError):
        engine.run_one_step(state)


def test_graph_engine_exposes_legal_targets_for_routing_layer() -> None:
    engine = GraphEngine(
        handlers={"interaction": lambda _state: NodeResult(next_node="finish", state_delta={})},
        legal_edges={"interaction": {"finish"}},
    )
    assert engine.legal_targets("interaction") == {"finish"}
