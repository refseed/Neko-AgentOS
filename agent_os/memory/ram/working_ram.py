from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkingRam:
    """Minimal active context per run."""

    _store: dict[str, dict[str, object]] = field(default_factory=dict)

    def put(self, run_id: str, key: str, value: object) -> str:
        self._store.setdefault(run_id, {})[key] = value
        return f"ram:{run_id}:{key}"

    def get(self, run_id: str, key: str) -> object | None:
        return self._store.get(run_id, {}).get(key)
