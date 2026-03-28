from __future__ import annotations

from agent_os.runtime.graph.blueprint_loader import build_blueprint_graph


def test_blueprint_loader_builds_default_graph() -> None:
    graph = build_blueprint_graph()
    assert graph.start_node == "literature_scan"
    assert "idea_summary" in graph.nodes


def test_blueprint_loader_rejects_illegal_jump() -> None:
    graph = build_blueprint_graph()
    assert graph.is_legal_exit("literature_scan", "writing_plan") is False


def test_blueprint_loader_resolves_stage_transition_by_result() -> None:
    graph = build_blueprint_graph()
    next_stage = graph.resolve_next_stage("idea_summary", "approved")
    assert next_stage == "writing_plan"


def test_blueprint_loader_exposes_runtime_template_constraints() -> None:
    graph = build_blueprint_graph()
    legal_targets = {"reasoning", "investigation", "reflection", "finish"}
    constrained = graph.constrain_runtime_targets("investigate_and_distill", legal_targets)
    assert constrained == {"reasoning", "investigation", "reflection"}
