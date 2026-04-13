"""Harness telemetry — tracks success rates and performance metrics.

Collects metrics per dispatch type, model, and operation to help
identify reliability issues and optimization opportunities.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class OperationMetric:
    """Metrics for a single category of operations."""
    total: int = 0
    successes: int = 0
    failures: int = 0
    fast_path_used: int = 0
    total_duration_ms: int = 0
    retries: int = 0

    @property
    def success_rate(self) -> float:
        return self.successes / self.total if self.total > 0 else 0.0

    @property
    def fast_path_rate(self) -> float:
        return self.fast_path_used / self.total if self.total > 0 else 0.0

    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / self.total if self.total > 0 else 0.0


class HarnessTelemetry:
    """Collects and reports harness performance metrics."""

    def __init__(self):
        self._dispatch_metrics: dict[str, OperationMetric] = defaultdict(OperationMetric)
        self._query_metrics = OperationMetric()
        self._model_metrics: dict[str, OperationMetric] = defaultdict(OperationMetric)

    def record_note(
        self,
        dispatch_type: str,
        model_used: str,
        success: bool,
        fast_path: bool,
        duration_ms: int,
        retried: bool = False,
    ) -> None:
        """Record a note processing operation."""
        m = self._dispatch_metrics[dispatch_type]
        m.total += 1
        if success:
            m.successes += 1
        else:
            m.failures += 1
        if fast_path:
            m.fast_path_used += 1
        m.total_duration_ms += duration_ms
        if retried:
            m.retries += 1

        mm = self._model_metrics[model_used]
        mm.total += 1
        if success:
            mm.successes += 1
        else:
            mm.failures += 1
        mm.total_duration_ms += duration_ms

    def record_query(
        self,
        success: bool,
        duration_ms: int,
        cached: bool = False,
    ) -> None:
        """Record a query operation."""
        self._query_metrics.total += 1
        if success:
            self._query_metrics.successes += 1
        else:
            self._query_metrics.failures += 1
        self._query_metrics.total_duration_ms += duration_ms
        if cached:
            self._query_metrics.fast_path_used += 1  # reuse field for cache hits

    def get_report(self) -> dict:
        """Get a telemetry report."""
        return {
            "dispatch": {
                dtype: {
                    "total": m.total,
                    "success_rate": round(m.success_rate, 2),
                    "fast_path_rate": round(m.fast_path_rate, 2),
                    "avg_duration_ms": round(m.avg_duration_ms),
                    "retries": m.retries,
                }
                for dtype, m in self._dispatch_metrics.items()
            },
            "queries": {
                "total": self._query_metrics.total,
                "success_rate": round(self._query_metrics.success_rate, 2),
                "cache_hit_rate": round(self._query_metrics.fast_path_rate, 2),
                "avg_duration_ms": round(self._query_metrics.avg_duration_ms),
            },
            "models": {
                model: {
                    "total": m.total,
                    "success_rate": round(m.success_rate, 2),
                    "avg_duration_ms": round(m.avg_duration_ms),
                }
                for model, m in self._model_metrics.items()
            },
        }
