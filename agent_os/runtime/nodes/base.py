from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from agent_os.models.json_parser import parse_json_as_model

NODE_PROTOCOL_VERSION = "node-io/v1"


class NodeGateway(Protocol):
    def request(self, prompt: str, model_tier: str):  # pragma: no cover - protocol
        ...


class NodeEnvelope(BaseModel):
    """Common protocol envelope required for every model-driven node output."""

    model_config = ConfigDict(extra="forbid")

    protocol_version: str = NODE_PROTOCOL_VERSION
    node_name: str
    confidence: float = 0.8
    notes: list[str] = Field(default_factory=list)


class NodeEnvelopeMixin(BaseModel):
    """Mixin for node-specific output models."""

    model_config = ConfigDict(extra="forbid")

    protocol_version: str = NODE_PROTOCOL_VERSION
    node_name: str = ""
    confidence: float = 0.8
    notes: list[str] = Field(default_factory=list)


InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=NodeEnvelopeMixin)


class BaseLLMNode(ABC, Generic[InputT, OutputT]):
    """Base class for model-driven nodes with a shared JSON protocol."""

    def __init__(self, node_name: str, model_gateway: NodeGateway | None = None) -> None:
        self._node_name = node_name
        self._model_gateway = model_gateway

    @property
    @abstractmethod
    def output_model(self) -> type[OutputT]:
        raise NotImplementedError

    @abstractmethod
    def build_prompt(self, node_input: InputT) -> str:
        raise NotImplementedError

    @abstractmethod
    def fallback(self, node_input: InputT) -> OutputT:
        raise NotImplementedError

    def run(self, node_input: InputT, model_tier: str) -> OutputT:
        fallback = self.fallback(node_input)
        if self._model_gateway is None:
            return fallback

        prompt = self.build_prompt(node_input)
        try:
            response = self._model_gateway.request(prompt=prompt, model_tier=model_tier)
        except Exception:
            return fallback

        parsed = parse_json_as_model(response.text, self.output_model)
        if parsed is None:
            return fallback
        if parsed.protocol_version != NODE_PROTOCOL_VERSION:
            return fallback
        if parsed.node_name and parsed.node_name != self._node_name:
            return fallback
        return parsed

