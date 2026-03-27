from __future__ import annotations

from agent_os.observability.tracing.trace_logger import TraceLogger


def test_trace_logger_writes_jsonl(tmp_path) -> None:
    logger = TraceLogger(tmp_path / "traces")
    event = logger.log(trace_id="trace_demo", event_type="node_start", message="start")
    trace_file = tmp_path / "traces" / "trace_demo.jsonl"

    assert event.trace_id == "trace_demo"
    assert trace_file.exists()
    assert trace_file.read_text(encoding="utf-8").strip()
