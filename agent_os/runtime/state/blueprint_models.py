from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SubgraphTemplateSpec(BaseModel):
    """Executable template constraints for one blueprint stage."""

    model_config = ConfigDict(extra="forbid")

    template_id: str
    allowed_runtime_targets: list[str] = Field(default_factory=list)
    preferred_entry: str | None = None


class BlueprintNode(BaseModel):
    """One allowed stage in the fixed project plan."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    goal: str
    allowed_exits: list[str] = Field(default_factory=list)
    subgraph_template: str
    checklist: list[str] = Field(default_factory=list)
    transition_on_result: dict[str, str] = Field(default_factory=dict)


class BlueprintGraph(BaseModel):
    """Static stage graph with explicit legal exits."""

    model_config = ConfigDict(extra="forbid")

    graph_id: str = "bp_default"
    start_node: str
    nodes: dict[str, BlueprintNode]
    subgraph_templates: dict[str, SubgraphTemplateSpec] = Field(default_factory=dict)

    def is_legal_exit(self, node_id: str, next_node: str) -> bool:
        if node_id not in self.nodes:
            return False
        return next_node in self.nodes[node_id].allowed_exits

    def resolve_next_stage(self, node_id: str, result: str) -> str | None:
        node = self.nodes.get(node_id)
        if node is None:
            return None
        next_stage = node.transition_on_result.get(result)
        if next_stage is None:
            return None
        if next_stage not in node.allowed_exits:
            return None
        return next_stage

    def constrain_runtime_targets(self, subgraph_template: str, runtime_targets: set[str]) -> set[str]:
        """Intersect graph-legal targets with template-legal runtime nodes."""

        template = self.subgraph_templates.get(subgraph_template)
        if template is None or not template.allowed_runtime_targets:
            return set(runtime_targets)
        allowed = set(template.allowed_runtime_targets)
        return {target for target in runtime_targets if target in allowed}
