from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EpisodicCache:
    """Append-only run event cache."""

    _events: dict[str, list[dict[str, object]]] = field(default_factory=dict)

    def append(self, run_id: str, event: dict[str, object]) -> str:
        self._events.setdefault(run_id, []).append(event)
        return f"cache:{run_id}:{len(self._events[run_id]) - 1}"

    def load(self, run_id: str) -> list[dict[str, object]]:
        return list(self._events.get(run_id, []))

    def load_by_ref(self, ref_id: str) -> dict[str, object] | None:
        parts = ref_id.split(":")
        if len(parts) != 3:
            return None
        prefix, run_id, index_text = parts
        if prefix != "cache" or not index_text.isdigit():
            return None
        events = self._events.get(run_id, [])
        index = int(index_text)
        if index < 0 or index >= len(events):
            return None
        return dict(events[index])
