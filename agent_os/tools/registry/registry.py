from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agent_os.tools.adapters.base import ToolContext

ToolHandler = Callable[[ToolContext, dict[str, object]], dict[str, object]]


@dataclass(frozen=True)
class ToolSpec:
    """Describe one tool the runtime may expose."""

    name: str
    description: str
    permission_level: str
    handler: ToolHandler


class ToolRegistry:
    """In-memory tool registry."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list_all(self) -> list[ToolSpec]:
        return list(self._tools.values())
