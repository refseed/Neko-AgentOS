from __future__ import annotations

from dataclasses import dataclass, field
from pydantic import BaseModel, ConfigDict, Field

from agent_os.runtime.nodes.base import BaseLLMNode, NodeEnvelopeMixin, NodeGateway


@dataclass(frozen=True)
class CompressionPack:
    l1: str
    l2: str
    l3: str
    forgotten_items: list[str] = field(default_factory=list)


class CompressionInput(BaseModel):
    """Protocol input for memory compression node."""

    model_config = ConfigDict(extra="forbid")

    text: str


class CompressionOutput(NodeEnvelopeMixin):
    """Protocol output for memory compression node."""

    node_name: str = "memory_compression"
    l1: str
    l2: str
    l3: str
    forgotten_items: list[str] = Field(default_factory=list)


class ForgettingInput(BaseModel):
    """Protocol input for forgetting node."""

    model_config = ConfigDict(extra="forbid")

    cache_refs: list[str]
    keep_limit: int


class ForgettingOutput(NodeEnvelopeMixin):
    """Protocol output for forgetting node."""

    node_name: str = "memory_forgetting"
    keep_indexes: list[int] = Field(default_factory=list)


class MemoryCompressionNode(BaseLLMNode[CompressionInput, CompressionOutput]):
    """Model-driven memory compression node."""

    @property
    def output_model(self) -> type[CompressionOutput]:
        return CompressionOutput

    def _fallback_pack(self, text: str) -> CompressionPack:
        normalized = " ".join(text.split())
        l3 = normalized
        l2 = normalized[:300]
        l1 = normalized[:120]
        return CompressionPack(l1=l1, l2=l2, l3=l3, forgotten_items=[])

    def fallback(self, node_input: CompressionInput) -> CompressionOutput:
        fallback = self._fallback_pack(node_input.text)
        return CompressionOutput(
            protocol_version="node-io/v1",
            node_name="memory_compression",
            confidence=0.72,
            notes=["fallback_compression"],
            l1=fallback.l1,
            l2=fallback.l2,
            l3=fallback.l3,
            forgotten_items=[],
        )

    def build_prompt(self, node_input: CompressionInput) -> str:
        normalized = " ".join(node_input.text.split())
        return (
            "You are a memory-compression and forgetting node.\n"
            "Compress text into L1/L2/L3 summaries.\n"
            "Protocol:\n"
            "- Return strict JSON only.\n"
            "- Required keys: protocol_version, node_name, confidence, notes, l1, l2, l3, forgotten_items.\n"
            "- protocol_version must be 'node-io/v1'.\n"
            "- node_name must be 'memory_compression'.\n"
            f"text:\n{normalized[:5000]}\n"
        )

    def compress(self, text: str, model_tier: str) -> CompressionPack:
        output = self.run(CompressionInput(text=text), model_tier=model_tier)
        return CompressionPack(
            l1=output.l1,
            l2=output.l2,
            l3=output.l3,
            forgotten_items=list(output.forgotten_items),
        )


class MemoryForgettingNode(BaseLLMNode[ForgettingInput, ForgettingOutput]):
    """Model-driven forgetting node for cache refs."""

    @property
    def output_model(self) -> type[ForgettingOutput]:
        return ForgettingOutput

    def fallback(self, node_input: ForgettingInput) -> ForgettingOutput:
        start = max(0, len(node_input.cache_refs) - node_input.keep_limit)
        return ForgettingOutput(
            protocol_version="node-io/v1",
            node_name="memory_forgetting",
            confidence=0.7,
            notes=["fallback_keep_recent"],
            keep_indexes=list(range(start, len(node_input.cache_refs))),
        )

    def build_prompt(self, node_input: ForgettingInput) -> str:
        return (
            "You are a memory forgetting node.\n"
            "Given ordered cache refs, keep the most useful subset.\n"
            "Protocol:\n"
            "- Return strict JSON only.\n"
            "- Required keys: protocol_version, node_name, confidence, notes, keep_indexes.\n"
            "- protocol_version must be 'node-io/v1'.\n"
            "- node_name must be 'memory_forgetting'.\n"
            f"keep_limit={node_input.keep_limit}\n"
            f"cache_refs={node_input.cache_refs}\n"
        )

    def select_refs(self, cache_refs: list[str], keep_limit: int, model_tier: str) -> list[str]:
        output = self.run(ForgettingInput(cache_refs=cache_refs, keep_limit=keep_limit), model_tier=model_tier)
        keep_indexes: list[int] = []
        for raw in output.keep_indexes:
            if isinstance(raw, int) and 0 <= raw < len(cache_refs):
                keep_indexes.append(raw)
        keep_indexes = sorted(dict.fromkeys(keep_indexes))[:keep_limit]
        if not keep_indexes:
            start = max(0, len(cache_refs) - keep_limit)
            keep_indexes = list(range(start, len(cache_refs)))
        kept = [cache_refs[idx] for idx in keep_indexes]
        return kept[-keep_limit:]


def compress_text(
    text: str,
    model_gateway: NodeGateway | None = None,
    model_tier: str = "small",
) -> CompressionPack:
    node = MemoryCompressionNode(node_name="memory_compression", model_gateway=model_gateway)
    return node.compress(text=text, model_tier=model_tier)


def keep_cache_refs(
    cache_refs: list[str],
    model_gateway: NodeGateway | None = None,
    model_tier: str = "small",
    keep_limit: int = 12,
) -> list[str]:
    """Model-driven forgetting for episodic cache refs with safe fallback."""

    if keep_limit <= 0:
        return []
    if len(cache_refs) <= keep_limit:
        return list(cache_refs)

    node = MemoryForgettingNode(node_name="memory_forgetting", model_gateway=model_gateway)
    return node.select_refs(cache_refs=cache_refs, keep_limit=keep_limit, model_tier=model_tier)
