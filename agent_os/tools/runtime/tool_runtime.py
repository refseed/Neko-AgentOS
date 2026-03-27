from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agent_os.tools.adapters.base import ToolContext
from agent_os.tools.registry.registry import ToolRegistry
from agent_os.tools.sandbox.sandbox import ToolSandbox


@dataclass(frozen=True)
class ToolExecutionResult:
    ok: bool
    tool_name: str
    output: dict[str, object]
    reason: str


class ToolRuntime:
    """Execute registered tools through sandbox and audit callback."""

    def __init__(
        self,
        registry: ToolRegistry,
        sandbox: ToolSandbox,
        audit_callback: Callable[[str, str, dict[str, object]], None] | None = None,
    ) -> None:
        self._registry = registry
        self._sandbox = sandbox
        self._audit_callback = audit_callback

    def execute(
        self,
        tool_name: str,
        run_id: str,
        permission_level: str,
        payload: dict[str, object],
        allowed_tools: set[str] | None = None,
    ) -> ToolExecutionResult:
        if allowed_tools is not None and tool_name not in allowed_tools:
            self._emit(
                "tool_blocked",
                tool_name,
                {"reason": "tool_not_loaded", "payload": payload, "run_id": run_id},
            )
            return ToolExecutionResult(
                ok=False,
                tool_name=tool_name,
                output={},
                reason="tool_not_loaded",
            )

        spec = self._registry.get(tool_name)
        if spec is None:
            self._emit("tool_missing", tool_name, {"reason": "not_registered", "run_id": run_id})
            return ToolExecutionResult(
                ok=False,
                tool_name=tool_name,
                output={},
                reason="tool_not_registered",
            )

        context = ToolContext(run_id=run_id, permission_level=permission_level)
        sandbox_result = self._sandbox.execute(spec, context, payload)
        if not sandbox_result.allowed:
            self._emit(
                "tool_blocked",
                tool_name,
                {"reason": sandbox_result.reason, "payload": payload, "run_id": run_id},
            )
            return ToolExecutionResult(
                ok=False,
                tool_name=tool_name,
                output={},
                reason=sandbox_result.reason,
            )

        self._emit("tool_executed", tool_name, {"payload": payload, "run_id": run_id})
        return ToolExecutionResult(
            ok=True,
            tool_name=tool_name,
            output=sandbox_result.output,
            reason="ok",
        )

    def _emit(self, event_type: str, tool_name: str, details: dict[str, object]) -> None:
        if self._audit_callback is None:
            return
        self._audit_callback(event_type, tool_name, details)
