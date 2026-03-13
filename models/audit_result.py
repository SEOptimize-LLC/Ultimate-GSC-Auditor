"""Audit result container with health scoring."""

from dataclasses import dataclass, field
from typing import Optional

from models.metric_result import MetricResult, Severity


@dataclass
class AuditResult:
    """Container for all metric results from an audit run."""

    property_url: str
    start_date: str
    end_date: str
    metrics_executed: list[int] = field(default_factory=list)
    results: list[MetricResult] = field(default_factory=list)
    ai_group_analyses: dict[str, str] = field(default_factory=dict)
    ai_executive_summary: Optional[str] = None
    ai_content_plan: Optional[str] = None

    def add_result(self, result: MetricResult) -> None:
        """Add a metric result."""
        self.results.append(result)

    def add_results(self, results: list[MetricResult]) -> None:
        """Add multiple metric results."""
        self.results.extend(results)

    @property
    def total_findings(self) -> int:
        return len(self.results)

    @property
    def health_score(self) -> int:
        """Calculate overall health score (0-100)."""
        score = 100
        for r in self.results:
            score -= r.severity.health_penalty
        return max(0, min(100, score))

    @property
    def health_grade(self) -> str:
        """Convert health score to letter grade."""
        score = self.health_score
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        return "F"

    @property
    def severity_counts(self) -> dict[str, int]:
        """Count findings by severity."""
        counts = {s.value: 0 for s in Severity}
        for r in self.results:
            counts[r.severity.value] += 1
        return counts

    @property
    def results_by_category(self) -> dict[str, list[MetricResult]]:
        """Group results by category."""
        grouped: dict[str, list[MetricResult]] = {}
        for r in self.results:
            grouped.setdefault(r.category, []).append(r)
        return grouped

    @property
    def results_by_severity(self) -> dict[str, list[MetricResult]]:
        """Group results by severity."""
        grouped: dict[str, list[MetricResult]] = {}
        for r in self.results:
            grouped.setdefault(r.severity.value, []).append(r)
        return grouped

    def get_top_findings(self, n: int = 10) -> list[MetricResult]:
        """Get the top N most severe findings."""
        sorted_results = sorted(self.results, key=lambda r: r.severity.priority)
        return sorted_results[:n]

    def to_dict(self) -> dict:
        """Serialize for storage in Supabase."""
        return {
            "property_url": self.property_url,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "metrics_executed": self.metrics_executed,
            "health_score": self.health_score,
            "health_grade": self.health_grade,
            "total_findings": self.total_findings,
            "severity_counts": self.severity_counts,
            "ai_executive_summary": self.ai_executive_summary,
            "ai_content_plan": self.ai_content_plan,
        }
