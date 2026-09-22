"""Métricas en memoria, exportables en formato Prometheus.

No reemplaza un proveedor de observabilidad: permite establecer una línea base
sin añadir dependencias ni enviar datos de usuarios a terceros.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from threading import Lock


class Metrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
        self._histograms: dict[tuple[str, tuple[tuple[str, str], ...]], deque[float]] = defaultdict(
            lambda: deque(maxlen=2048),
        )
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    @staticmethod
    def _labels(labels: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((labels or {}).items()))

    def increment(self, name: str, labels: dict[str, str] | None = None, value: int = 1) -> None:
        with self._lock:
            self._counters[(name, self._labels(labels))] += value

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._histograms[(name, self._labels(labels))].append(value)

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._gauges[(name, self._labels(labels))] = value

    @staticmethod
    def _render_labels(labels: tuple[tuple[str, str], ...]) -> str:
        if not labels:
            return ""
        rendered = []
        for key, value in labels:
            safe_value = value.replace("\\", "\\\\").replace('"', '\\"')
            rendered.append(f'{key}="{safe_value}"')
        return "{" + ",".join(rendered) + "}"

    def prometheus(self) -> str:
        with self._lock:
            counters = list(self._counters.items())
            histograms = [(key, list(values)) for key, values in self._histograms.items()]
            gauges = list(self._gauges.items())

        lines = ["# Metrics are per API process; aggregate them in your metrics collector."]
        for (name, labels), value in counters:
            lines.append(f"{name}_total{self._render_labels(labels)} {value}")
        for (name, labels), values in histograms:
            if not values:
                continue
            rendered = self._render_labels(labels)
            lines.append(f"{name}_count{rendered} {len(values)}")
            lines.append(f"{name}_sum{rendered} {sum(values):.6f}")
            lines.append(f"{name}_max{rendered} {max(values):.6f}")
            p95_index = max(0, int(len(values) * 0.95) - 1)
            lines.append(f"{name}_p95{rendered} {sorted(values)[p95_index]:.6f}")
        for (name, labels), value in gauges:
            lines.append(f"{name}{self._render_labels(labels)} {value}")
        return "\n".join(lines) + "\n"


metrics = Metrics()
