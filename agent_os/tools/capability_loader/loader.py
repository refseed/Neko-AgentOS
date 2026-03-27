from __future__ import annotations

from dataclasses import dataclass, field

from agent_os.tools.registry.registry import ToolRegistry, ToolSpec


@dataclass(frozen=True)
class CapabilitySelection:
    loaded: list[ToolSpec] = field(default_factory=list)
    withheld: list[ToolSpec] = field(default_factory=list)
    reason: str = ""


class CapabilityLoader:
    """Load tool subsets by node role and permission level."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def load(self, node_type: str, permission_level: str) -> CapabilitySelection:
        loaded: list[ToolSpec] = []
        withheld: list[ToolSpec] = []
        for tool in self._registry.list_all():
            if self._can_load(tool, node_type=node_type, permission_level=permission_level):
                loaded.append(tool)
            else:
                withheld.append(tool)
        reason = f"{node_type}_{permission_level}"
        return CapabilitySelection(loaded=loaded, withheld=withheld, reason=reason)

    def _can_load(self, tool: ToolSpec, node_type: str, permission_level: str) -> bool:
        if permission_level == "none":
            return False
        if permission_level == "readonly" and tool.permission_level != "readonly":
            return False
        if node_type == "investigation":
            return tool.permission_level == "readonly"
        return True
