from __future__ import annotations

from agent_os.tools.adapters.base import ToolContext
from agent_os.tools.capability_loader.loader import CapabilityLoader
from agent_os.tools.registry.registry import ToolRegistry, ToolSpec
from agent_os.tools.runtime.tool_runtime import ToolRuntime
from agent_os.tools.sandbox.sandbox import ToolSandbox


def test_capability_loader_exposes_readonly_tools_for_investigation() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="read_doc",
            description="read",
            permission_level="readonly",
            handler=lambda _ctx, _payload: {"ok": True},
        )
    )
    registry.register(
        ToolSpec(
            name="write_doc",
            description="write",
            permission_level="write",
            handler=lambda _ctx, _payload: {"ok": True},
        )
    )
    loader = CapabilityLoader(registry)
    selection = loader.load(node_type="investigation", permission_level="readonly")
    assert [tool.name for tool in selection.loaded] == ["read_doc"]


def test_sandbox_blocks_high_risk_tool_in_readonly_mode(tmp_path) -> None:
    tool = ToolSpec(
        name="write_doc",
        description="write",
        permission_level="write",
        handler=lambda _ctx, _payload: {"ok": True},
    )
    sandbox = ToolSandbox(allowed_roots=[tmp_path])
    context = ToolContext(run_id="run1", permission_level="readonly")
    result = sandbox.execute(tool, context, {"path": str(tmp_path / "file.txt")})
    assert result.allowed is False
    assert result.reason == "permission_denied"


def test_capability_loader_hides_all_tools_when_permission_none() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="read_doc",
            description="read",
            permission_level="readonly",
            handler=lambda _ctx, _payload: {"ok": True},
        )
    )
    loader = CapabilityLoader(registry)
    selection = loader.load(node_type="break", permission_level="none")
    assert selection.loaded == []


def test_tool_runtime_reports_blocked_action(tmp_path) -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="write_doc",
            description="write",
            permission_level="write",
            handler=lambda _ctx, _payload: {"ok": True},
        )
    )
    runtime = ToolRuntime(
        registry=registry,
        sandbox=ToolSandbox(allowed_roots=[tmp_path]),
        audit_callback=lambda event_type, tool_name, details: events.append((event_type, tool_name, details)),
    )

    result = runtime.execute(
        tool_name="write_doc",
        run_id="run1",
        permission_level="readonly",
        payload={"path": str(tmp_path / "x.txt")},
    )
    assert result.ok is False
    assert events
    assert events[-1][0] == "tool_blocked"


def test_tool_runtime_blocks_when_tool_not_loaded(tmp_path) -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="read_doc",
            description="read",
            permission_level="readonly",
            handler=lambda _ctx, _payload: {"ok": True},
        )
    )
    runtime = ToolRuntime(
        registry=registry,
        sandbox=ToolSandbox(allowed_roots=[tmp_path]),
    )
    result = runtime.execute(
        tool_name="read_doc",
        run_id="run1",
        permission_level="readonly",
        payload={"path": str(tmp_path / "a.txt")},
        allowed_tools={"other_tool"},
    )
    assert result.ok is False
    assert result.reason == "tool_not_loaded"


def test_sandbox_blocks_permission_none(tmp_path) -> None:
    tool = ToolSpec(
        name="read_doc",
        description="read",
        permission_level="readonly",
        handler=lambda _ctx, _payload: {"ok": True},
    )
    sandbox = ToolSandbox(allowed_roots=[tmp_path])
    context = ToolContext(run_id="run1", permission_level="none")
    result = sandbox.execute(tool, context, {"path": str(tmp_path / "file.txt")})
    assert result.allowed is False
    assert result.reason == "permission_none"
