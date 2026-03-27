from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field


class ProviderResponse(BaseModel):
    """Provider-specific response normalized before gateway output."""

    model_config = ConfigDict(extra="forbid")

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw: dict[str, object] = Field(default_factory=dict)


class BaseProvider(ABC):
    """Base provider interface for model backends."""

    @abstractmethod
    def generate(self, prompt: str, model_tier: str) -> ProviderResponse:
        raise NotImplementedError


class EchoProvider(BaseProvider):
    """Deterministic local provider for tests and offline runs."""

    def generate(self, prompt: str, model_tier: str) -> ProviderResponse:
        text = (
            "Draft based on current evidence. "
            "If evidence is missing, investigation should gather source-backed facts."
        )
        return ProviderResponse(
            text=text,
            input_tokens=max(1, len(prompt.split())),
            output_tokens=max(1, len(text.split())),
            raw={"provider": "echo", "model_tier": model_tier},
        )
