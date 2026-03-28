from __future__ import annotations

from agent_os.runtime.state.blueprint_models import BlueprintGraph, BlueprintNode, SubgraphTemplateSpec


def build_blueprint_graph(nodes: list[BlueprintNode] | None = None) -> BlueprintGraph:
    """Build a blueprint graph from data or fallback sample flow."""

    if nodes is None:
        nodes = [
            BlueprintNode(
                node_id="literature_scan",
                goal="collect evidence from sources",
                allowed_exits=["idea_summary"],
                subgraph_template="investigate_and_distill",
                checklist=["find at least two grounded facts"],
                transition_on_result={
                    "approved": "idea_summary",
                    "retry": "literature_scan",
                    "need_more_evidence": "literature_scan",
                },
            ),
            BlueprintNode(
                node_id="idea_summary",
                goal="build a concise idea summary with evidence",
                allowed_exits=["writing_plan", "literature_scan"],
                subgraph_template="reason_reflect_loop",
                checklist=["state what is known", "state what is missing"],
                transition_on_result={
                    "approved": "writing_plan",
                    "retry": "idea_summary",
                    "need_more_evidence": "literature_scan",
                },
            ),
            BlueprintNode(
                node_id="writing_plan",
                goal="produce a structured writing plan",
                allowed_exits=["done", "idea_summary"],
                subgraph_template="compose_outline",
                checklist=["keep claims traceable to facts"],
                transition_on_result={
                    "approved": "done",
                    "retry": "writing_plan",
                    "need_more_evidence": "idea_summary",
                },
            ),
            BlueprintNode(
                node_id="done",
                goal="finish run",
                allowed_exits=[],
                subgraph_template="terminal",
                checklist=[],
                transition_on_result={},
            ),
        ]

    node_map = {node.node_id: node for node in nodes}
    template_specs = {
        "investigate_and_distill": SubgraphTemplateSpec(
            template_id="investigate_and_distill",
            allowed_runtime_targets=["reasoning", "investigation", "reflection", "break"],
            preferred_entry="reasoning",
        ),
        "reason_reflect_loop": SubgraphTemplateSpec(
            template_id="reason_reflect_loop",
            allowed_runtime_targets=["reasoning", "reflection", "investigation", "break"],
            preferred_entry="reasoning",
        ),
        "compose_outline": SubgraphTemplateSpec(
            template_id="compose_outline",
            allowed_runtime_targets=["reasoning", "reflection", "break"],
            preferred_entry="reasoning",
        ),
        "terminal": SubgraphTemplateSpec(
            template_id="terminal",
            allowed_runtime_targets=["finish", "break", "blueprint"],
            preferred_entry="finish",
        ),
    }
    return BlueprintGraph(
        graph_id="bp_default",
        start_node="literature_scan",
        nodes=node_map,
        subgraph_templates=template_specs,
    )
