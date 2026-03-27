from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agent_os.runtime.state.models import RunState


class GraphRuntimeError(RuntimeError):
    """Raised when runtime cannot execute the current node safely."""


class IllegalEdgeError(GraphRuntimeError):
    """Raised when a node tries to jump through a forbidden edge."""


@dataclass(frozen=True)
class NodeResult:
    """Result produced by one runtime node."""

    next_node: str
    state_delta: dict[str, object]


NodeHandler = Callable[[RunState], NodeResult]


class GraphEngine:
    """Run one node and return the next legal state."""

    def __init__(
        self,
        handlers: dict[str, NodeHandler],
        legal_edges: dict[str, set[str]],
        *,
        increment_budget: bool = True,
    ) -> None:
        self._handlers = handlers
        self._legal_edges = legal_edges
        self._increment_budget = increment_budget

    def apply_delta(self, state: RunState, state_delta: dict[str, object]) -> RunState:
        # Invariant: only routing logic controls current_node transitions.
        if "current_node" in state_delta:
            raise GraphRuntimeError("state_delta must not include current_node")
        return state.model_copy(update=state_delta).touch()

    def legal_targets(self, source: str) -> set[str]:
        return set(self._legal_edges.get(source, set()))

    def run_one_step(self, state: RunState) -> RunState:
        if state.current_node not in self._handlers:
            raise GraphRuntimeError(f"no handler registered for node: {state.current_node}")

        handler = self._handlers[state.current_node]
        result = handler(state)
        self._assert_legal_edge(state.current_node, result.next_node)

        merged_delta = dict(result.state_delta)
        if self._increment_budget:
            updated_budget = result.state_delta.get("budget", state.budget)
            if not hasattr(updated_budget, "model_copy"):
                raise GraphRuntimeError("budget delta must be a BudgetState model instance")
            budget_delta = updated_budget.model_copy(update={"step_used": updated_budget.step_used + 1})
            merged_delta = {**result.state_delta, "budget": budget_delta}
        next_state = self.apply_delta(state, merged_delta)
        return next_state.model_copy(update={"current_node": result.next_node})

    def _assert_legal_edge(self, source: str, target: str) -> None:
        legal_targets = self._legal_edges.get(source, set())
        if target not in legal_targets:
            raise IllegalEdgeError(f"illegal edge: {source} -> {target}")
