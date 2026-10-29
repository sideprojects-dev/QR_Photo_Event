"""Optional, privacy-safe timing events for application operations."""

import json
import logging
import os
import time
from contextlib import contextmanager
from secrets import token_hex


_logger = logging.getLogger("uvicorn.error")
_TRUE_VALUES = {"1", "true", "yes", "on"}


def monitoring_enabled() -> bool:
    return os.getenv("QR_PERF_MONITORING", "").strip().lower() in _TRUE_VALUES


class PerfTrace:
    def __init__(self, operation: str, trace_id: str | None = None):
        self.enabled = monitoring_enabled()
        self.operation = operation
        self.trace_id = (trace_id or token_hex(8)) if self.enabled else None
        self.started = time.perf_counter() if self.enabled else None
        self.phases = {}

    @contextmanager
    def step(self, name: str):
        if not self.enabled:
            yield
            return
        started = time.perf_counter()
        try:
            yield
        finally:
            self.phases[name] = round(
                self.phases.get(name, 0) + (time.perf_counter() - started) * 1000, 2
            )

    def emit(self, outcome: str = "ok"):
        if not self.enabled:
            return
        event = {
            "event": "performance",
            "operation": self.operation,
            "trace_id": self.trace_id,
            "outcome": outcome,
            "total_ms": round((time.perf_counter() - self.started) * 1000, 2),
            "phases_ms": self.phases,
        }
        try:
            _logger.info(json.dumps(event, separators=(",", ":")))
        except Exception:
            # Telemetry must never change the application response or hold an upload slot.
            pass
