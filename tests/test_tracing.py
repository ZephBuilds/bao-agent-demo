import json
from pathlib import Path

import pytest

from app.tracing import JsonlTracer


def test_span_records_error_then_recovers_without_persisting_exception_message(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "trace.jsonl"
    tracer = JsonlTracer(trace_path)
    sensitive_message = "customer-token=do-not-persist"

    with pytest.raises(RuntimeError, match=sensitive_message):
        with tracer.span("failing_operation"):
            raise RuntimeError(sensitive_message)

    with tracer.span("recovery_operation") as result:
        result["records_processed"] = 1

    raw_trace = trace_path.read_text(encoding="utf-8")
    events = [json.loads(line) for line in raw_trace.splitlines()]

    assert len(events) == 2
    assert events[0]["action"] == "failing_operation"
    assert events[0]["status"] == "error"
    assert events[0]["error_type"] == "RuntimeError"
    assert sensitive_message not in raw_trace
    assert events[1]["action"] == "recovery_operation"
    assert events[1]["status"] == "ok"
    assert events[1]["records_processed"] == 1
