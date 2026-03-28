from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from agent_os.runtime.nodes.base import BaseLLMNode, NodeEnvelopeMixin, NodeGateway
from agent_os.runtime.state.models import RunState


class PromptBuildInput(BaseModel):
    """Protocol input for prompt-construction node."""

    model_config = ConfigDict(extra="forbid")

    node_mode: str
    goal: str
    stage: str
    instruction: str
    accepted_facts: list[str]
    memory_context: list[str]
    checklist: list[str]
    draft_text: str


class PromptBuildOutput(NodeEnvelopeMixin):
    """Protocol output for prompt-construction node."""

    node_name: str = "prompt_builder"
    prompt: str


class PromptBuilderNode(BaseLLMNode[PromptBuildInput, PromptBuildOutput]):
    """Model-driven prompt construction node."""

    @property
    def output_model(self) -> type[PromptBuildOutput]:
        return PromptBuildOutput

    def _reasoning_seed(self, node_input: PromptBuildInput) -> str:
        accepted_facts = "\n".join(f"- {fact}" for fact in node_input.accepted_facts[:8]) or "- none yet"
        memory_context = "\n".join(f"- {item}" for item in node_input.memory_context[:8]) or "- none mounted"
        return (
            f"Goal: {node_input.goal}\n"
            f"Blueprint stage: {node_input.stage}\n"
            f"Instruction: {node_input.instruction}\n"
            f"Accepted facts:\n{accepted_facts}\n"
            f"Mounted memory:\n{memory_context}\n"
            "Produce a concise draft. If facts are insufficient, list what is missing."
        )

    def _reflection_seed(self, node_input: PromptBuildInput) -> str:
        checklist_text = "\n".join(f"- {item}" for item in node_input.checklist) or "- Ensure claims are evidence-backed"
        facts_text = "\n".join(f"- {fact}" for fact in node_input.accepted_facts[:8]) or "- none yet"
        memory_text = "\n".join(f"- {item}" for item in node_input.memory_context[:8]) or "- none mounted"
        return (
            f"Stage: {node_input.stage}\n"
            f"Checklist:\n{checklist_text}\n"
            f"Accepted facts:\n{facts_text}\n"
            f"Mounted memory:\n{memory_text}\n"
            f"Draft:\n{node_input.draft_text}\n"
            "Review dimensions: intent alignment, logic consistency, completeness, uncertainty handling, and evidence use when required.\n"
            "Return one of: approved, retry, need_more_evidence."
        )

    def fallback(self, node_input: PromptBuildInput) -> PromptBuildOutput:
        seed = self._reasoning_seed(node_input) if node_input.node_mode == "reasoning" else self._reflection_seed(node_input)
        return PromptBuildOutput(
            protocol_version="node-io/v1",
            node_name="prompt_builder",
            confidence=0.75,
            notes=["fallback_seed_prompt"],
            prompt=seed,
        )

    def build_prompt(self, node_input: PromptBuildInput) -> str:
        seed = self._reasoning_seed(node_input) if node_input.node_mode == "reasoning" else self._reflection_seed(node_input)
        return (
            "You are a prompt-construction node in Agent OS.\n"
            "Protocol:\n"
            "- Return strict JSON only.\n"
            '- Required keys: protocol_version, node_name, confidence, notes, prompt.\n'
            "- protocol_version must be 'node-io/v1'.\n"
            "- node_name must be 'prompt_builder'.\n"
            f"node_mode={node_input.node_mode}\n"
            f"Seed prompt:\n{seed}\n"
        )


def build_reasoning_prompt(
    state: RunState,
    model_gateway: NodeGateway | None = None,
    model_tier: str | None = None,
) -> str:
    node = PromptBuilderNode(node_name="prompt_builder", model_gateway=model_gateway)
    output = node.run(
        PromptBuildInput(
            node_mode="reasoning",
            goal=state.goal,
            stage=state.blueprint.active_node,
            instruction=state.payload.instruction or state.goal,
            accepted_facts=list(state.payload.accepted_facts),
            memory_context=list(state.payload.memory_context),
            checklist=[],
            draft_text="",
        ),
        model_tier=model_tier or state.routing.model_tier,
    )
    return output.prompt


def build_reflection_prompt(
    state: RunState,
    draft_text: str,
    checklist: list[str],
    model_gateway: NodeGateway | None = None,
    model_tier: str | None = None,
) -> str:
    node = PromptBuilderNode(node_name="prompt_builder", model_gateway=model_gateway)
    output = node.run(
        PromptBuildInput(
            node_mode="reflection",
            goal=state.goal,
            stage=state.blueprint.active_node,
            instruction=state.payload.instruction or state.goal,
            accepted_facts=list(state.payload.accepted_facts),
            memory_context=list(state.payload.memory_context),
            checklist=list(checklist),
            draft_text=draft_text,
        ),
        model_tier=model_tier or state.routing.model_tier,
    )
    return output.prompt
