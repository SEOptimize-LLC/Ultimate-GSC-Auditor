"""Metric result data model.

Each metric computation returns one or more MetricResult objects
that capture the finding, its severity, and actionable recommendations.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import pandas as pd


class Severity(Enum):
    """Finding severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSIGHT = "insight"

    @property
    def priority(self) -> int:
        """Lower number = higher priority for sorting."""
        return {
            "critical": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
            "insight": 4,
        }[self.value]

    @property
    def color(self) -> str:
        return {
            "critical": "#DC3545",
            "high": "#FD7E14",
            "medium": "#FFC107",
            "low": "#0D6EFD",
            "insight": "#6C757D",
        }[self.value]

    @property
    def emoji(self) -> str:
        return {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🔵",
            "insight": "⚪",
        }[self.value]

    @property
    def health_penalty(self) -> int:
        """Points deducted from health score per finding of this severity."""
        return {
            "critical": 15,
            "high": 8,
            "medium": 3,
            "low": 1,
            "insight": 0,
        }[self.value]


class TrendDirection(Enum):
    """Direction of change for a metric."""
    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"
    NEW = "new"


@dataclass
class MetricResult:
    """Output of a single metric computation."""

    metric_id: int
    metric_name: str
    category: str
    severity: Severity
    summary: str
    computed_value: Optional[float] = None
    affected_count: int = 0
    opportunity_value: Optional[str] = None
    data_table: Optional[pd.DataFrame] = None
    recommendations: list[str] = field(default_factory=list)
    trend_direction: Optional[TrendDirection] = None
    benchmark_comparison: Optional[str] = None  # "above", "below", "at"
    details: Optional[dict] = None  # Additional context for AI analysis

    @property
    def data_table_limited(self) -> Optional[pd.DataFrame]:
        """Return data table limited to 25 rows for display."""
        if self.data_table is not None and not self.data_table.empty:
            return self.data_table.head(25)
        return None

    def to_dict(self) -> dict:
        """Serialize for storage in Supabase."""
        result = {
            "metric_id": self.metric_id,
            "metric_name": self.metric_name,
            "category": self.category,
            "severity": self.severity.value,
            "summary": self.summary,
            "computed_value": self.computed_value,
            "affected_count": self.affected_count,
            "opportunity_value": self.opportunity_value,
            "recommendations": self.recommendations,
            "trend_direction": self.trend_direction.value if self.trend_direction else None,
            "benchmark_comparison": self.benchmark_comparison,
        }
        if self.data_table is not None and not self.data_table.empty:
            result["data_snapshot"] = self.data_table.head(25).to_dict(orient="records")
        return result
