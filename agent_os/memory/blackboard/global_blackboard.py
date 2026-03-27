from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GlobalBlackboard:
    """Stable constants shared across the full run."""

    constants: dict[str, object] = field(default_factory=dict)

    def set_constant(self, key: str, value: object) -> None:
        self.constants[key] = value

    def get_constant(self, key: str) -> object | None:
        return self.constants.get(key)

    def render_context(self) -> list[str]:
        return [f"{key}: {value}" for key, value in self.constants.items()]
