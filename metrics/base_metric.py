"""Base class for metric group computations.

Each metric group (e.g., QueryPerformanceMetrics) inherits from
BaseMetricGroup and registers its metric methods in METRIC_REGISTRY.
"""

import logging
from abc import ABC
from typing import Optional

import pandas as pd

from core.data_store import DataStore
from models.data_shapes import METRIC_NAMES, get_category_for_metric
from models.metric_result import MetricResult, Severity, TrendDirection

logger = logging.getLogger(__name__)


class BaseMetricGroup(ABC):
    """Abstract base class for metric group implementations."""

    # Subclasses must define this: maps metric_id -> method_name
    METRIC_REGISTRY: dict[int, str] = {}

    def __init__(
        self,
        store: DataStore,
        brand_name: str = "",
        ai_classifications: Optional[dict] = None,
    ):
        self.store = store
        self.brand_name = brand_name
        self.ai_classifications = ai_classifications or {}

    def run_metrics(
        self, metric_ids: Optional[list[int]] = None
    ) -> list[MetricResult]:
        """Run selected metrics and return results.

        Args:
            metric_ids: Specific metric IDs to run. If None, runs all
                       metrics in this group's registry.
        """
        if metric_ids is None:
            ids_to_run = list(self.METRIC_REGISTRY.keys())
        else:
            ids_to_run = [
                mid for mid in metric_ids
                if mid in self.METRIC_REGISTRY
            ]

        results: list[MetricResult] = []
        for metric_id in sorted(ids_to_run):
            method_name = self.METRIC_REGISTRY[metric_id]
            method = getattr(self, method_name, None)
            if method is None:
                logger.warning(
                    f"Method {method_name} not found for metric {metric_id}"
                )
                continue

            try:
                metric_results = method()
                if isinstance(metric_results, list):
                    results.extend(metric_results)
                elif isinstance(metric_results, MetricResult):
                    results.append(metric_results)
            except Exception as e:
                logger.error(
                    f"Metric {metric_id} ({METRIC_NAMES.get(metric_id, '?')}) "
                    f"failed: {e}"
                )
                results.append(self._error_result(metric_id, str(e)))

        return results

    def get_df(self, shape_name: str) -> pd.DataFrame:
        """Get a DataFrame from the data store."""
        return self.store.get_df(shape_name)

    def create_result(
        self,
        metric_id: int,
        severity: Severity,
        summary: str,
        computed_value: Optional[float] = None,
        affected_count: int = 0,
        opportunity_value: Optional[str] = None,
        data_table: Optional[pd.DataFrame] = None,
        recommendations: Optional[list[str]] = None,
        trend_direction: Optional[TrendDirection] = None,
        benchmark_comparison: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> MetricResult:
        """Create a MetricResult with auto-filled name and category."""
        return MetricResult(
            metric_id=metric_id,
            metric_name=METRIC_NAMES.get(metric_id, f"Metric {metric_id}"),
            category=get_category_for_metric(metric_id),
            severity=severity,
            summary=summary,
            computed_value=computed_value,
            affected_count=affected_count,
            opportunity_value=opportunity_value,
            data_table=data_table,
            recommendations=recommendations or [],
            trend_direction=trend_direction,
            benchmark_comparison=benchmark_comparison,
            details=details,
        )

    def _error_result(self, metric_id: int, error_msg: str) -> MetricResult:
        """Create an error result when a metric computation fails."""
        return self.create_result(
            metric_id=metric_id,
            severity=Severity.INSIGHT,
            summary=f"Metric computation failed: {error_msg}",
            recommendations=["Check data availability and retry the audit."],
        )

    def is_branded_query(self, query: str) -> bool:
        """Check if a query is branded using AI classifications or fallback."""
        # Check AI classification cache first
        if query in self.ai_classifications:
            classification = self.ai_classifications[query]
            if isinstance(classification, dict) and "is_branded" in classification:
                return classification["is_branded"]

        # Fallback: simple string matching
        if self.brand_name:
            return self.brand_name.lower() in query.lower()
        return False

    def get_query_intent(self, query: str) -> Optional[str]:
        """Get the intent classification for a query."""
        if query in self.ai_classifications:
            classification = self.ai_classifications[query]
            if isinstance(classification, dict) and "intent" in classification:
                return classification["intent"]
        return None

    def get_topic_cluster(self, query: str) -> Optional[str]:
        """Get the topic cluster for a query."""
        if query in self.ai_classifications:
            classification = self.ai_classifications[query]
            if isinstance(classification, dict) and "topic_cluster" in classification:
                return classification["topic_cluster"]
        return None
