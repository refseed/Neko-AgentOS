from __future__ import annotations

from dataclasses import dataclass

from agent_os.runtime.state.models import RunState


@dataclass(frozen=True)
class CapabilityRoute:
    """Tool exposure decision for current node."""

    node_type: str
    permission_level: str
    reason: str


class CapabilityRouter:
    """Decide minimal tool permission per node and uncertainty state."""

    def __init__(self, permission_by_node: dict[str, str] | None = None) -> None:
        self._permission_by_node = permission_by_node or {}

    def route(self, state: RunState, next_node: str) -> CapabilityRoute:
        if state.uncertainty.status == "blocked":
            return CapabilityRoute(
                node_type=next_node,
                permission_level="none",
                reason="uncertainty_blocked",
            )

        permission = self._permission_by_node.get(next_node, "readonly")
        reason = f"profile_{next_node}_{permission}"
        return CapabilityRoute(node_type=next_node, permission_level=permission, reason=reason)
