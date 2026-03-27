from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolContext:
    """Runtime context passed into tool handlers."""

    run_id: str
    permission_level: str
    metadata: dict[str, object] = field(default_factory=dict)
