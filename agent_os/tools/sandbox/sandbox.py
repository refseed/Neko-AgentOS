from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_os.tools.adapters.base import ToolContext
from agent_os.tools.registry.registry import ToolSpec


@dataclass(frozen=True)
class SandboxResult:
    allowed: bool
    output: dict[str, object]
    reason: str


class ToolSandbox:
    """Guard side-effect tools with permission and path controls."""

    def __init__(self, allowed_roots: list[Path]) -> None:
        self._allowed_roots = [path.resolve() for path in allowed_roots]

    def execute(
        self,
        tool: ToolSpec,
        context: ToolContext,
        payload: dict[str, object],
    ) -> SandboxResult:
        if context.permission_level == "none":
            return SandboxResult(allowed=False, output={}, reason="permission_none")
        if context.permission_level == "readonly" and tool.permission_level != "readonly":
            return SandboxResult(allowed=False, output={}, reason="permission_denied")

        target_path = payload.get("path")
        if isinstance(target_path, str) and not self._is_path_allowed(Path(target_path)):
            return SandboxResult(allowed=False, output={}, reason="path_not_allowed")

        output = tool.handler(context, payload)
        return SandboxResult(allowed=True, output=output, reason="ok")

    def _is_path_allowed(self, target: Path) -> bool:
        resolved = target.resolve()
        return any(resolved.is_relative_to(root) for root in self._allowed_roots)
