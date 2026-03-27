from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class TraceEvent(BaseModel):
    """One structured event in the run history."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    event_type: str
    message: str
    timestamp: str
    details: dict[str, object] = Field(default_factory=dict)


class TraceLogger:
    """Append trace events to JSONL files."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._root_dir.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        trace_id: str,
        event_type: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> TraceEvent:
        event = TraceEvent(
            trace_id=trace_id,
            event_type=event_type,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=details or {},
        )
        trace_file = self._root_dir / f"{trace_id}.jsonl"
        with trace_file.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")
        return event
