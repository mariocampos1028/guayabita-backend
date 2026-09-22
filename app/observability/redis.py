"""Proxy que mide llamadas a Upstash sin cambiar la interfaz usada por la app."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from app.observability.metrics import metrics


class InstrumentedRedis:
    def __init__(self, client: Any) -> None:
        self._client = client

    def __getattr__(self, operation: str):
        target = getattr(self._client, operation)
        if not callable(target):
            return target

        def instrumented(*args: Any, **kwargs: Any):
            started = perf_counter()
            outcome = "ok"
            try:
                return target(*args, **kwargs)
            except Exception:
                outcome = "error"
                raise
            finally:
                labels = {"operation": operation, "outcome": outcome}
                metrics.increment("guayabita_redis_operations", labels)
                metrics.observe("guayabita_redis_operation_seconds", perf_counter() - started, labels)

        return instrumented
