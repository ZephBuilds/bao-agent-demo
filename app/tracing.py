import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JsonlTracer:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: dict[str, Any]) -> None:
        payload = {"timestamp": datetime.now(UTC).isoformat(), **event}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    @contextmanager
    def span(self, action: str, **metadata: Any) -> Iterator[dict[str, Any]]:
        started = time.perf_counter()
        result: dict[str, Any] = {}
        try:
            yield result
        except Exception as exc:
            self.emit(
                {
                    "action": action,
                    "status": "error",
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "error_type": type(exc).__name__,
                    **metadata,
                }
            )
            raise
        else:
            self.emit(
                {
                    "action": action,
                    "status": "ok",
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    **metadata,
                    **result,
                }
            )
