"""Metrics package — 100 custom SEO metric computations.

Routes metric IDs to the appropriate metric group class.
"""

from typing import Optional

from core.data_store import DataStore
from metrics.base_metric import BaseMetricGroup
from metrics.query_performance import QueryPerformanceMetrics
from metrics.click_ctr import ClickCTRMetrics
from metrics.impression_visibility import (
    ImpressionVisibilityMetrics,
)
from metrics.position_ranking import PositionRankingMetrics
from metrics.crawl_index_health import CrawlIndexHealthMetrics
from metrics.content_health import ContentHealthMetrics
from metrics.device_segment import DeviceSegmentMetrics
from metrics.indexation_coverage import (
    IndexationCoverageMetrics,
)
from metrics.content_portfolio import ContentPortfolioMetrics
from metrics.query_intent_topical import (
    QueryIntentTopicalMetrics,
)
from metrics.click_behavior import ClickBehaviorMetrics
from metrics.impression_quality import (
    ImpressionQualityMetrics,
)
from metrics.ranking_velocity import RankingVelocityMetrics


# Maps metric ID ranges to their group classes
METRIC_GROUP_CLASSES: list[
    tuple[range, type[BaseMetricGroup]]
] = [
    (range(1, 13), QueryPerformanceMetrics),
    (range(13, 22), ClickCTRMetrics),
    (range(22, 28), ImpressionVisibilityMetrics),
    (range(28, 35), PositionRankingMetrics),
    (range(35, 45), CrawlIndexHealthMetrics),
    (range(45, 49), ContentHealthMetrics),
    (range(49, 51), DeviceSegmentMetrics),
    (range(51, 61), QueryIntentTopicalMetrics),
    (range(61, 69), ClickBehaviorMetrics),
    (range(69, 78), ImpressionQualityMetrics),
    (range(78, 85), RankingVelocityMetrics),
    (range(85, 95), IndexationCoverageMetrics),
    (range(95, 101), ContentPortfolioMetrics),
]


def get_metric_groups(
    metric_ids: list[int],
    store: DataStore,
    brand_name: str = "",
    ai_classifications: Optional[dict] = None,
) -> list[BaseMetricGroup]:
    """Instantiate the metric group classes needed for the given metric IDs.

    Returns a list of instantiated groups, each configured with only
    the metric IDs relevant to that group.
    """
    needed_classes: dict[type[BaseMetricGroup], list[int]] = {}

    for mid in metric_ids:
        for id_range, cls in METRIC_GROUP_CLASSES:
            if mid in id_range:
                needed_classes.setdefault(cls, []).append(mid)
                break

    groups = []
    for cls, ids in needed_classes.items():
        group = cls(
            store=store,
            brand_name=brand_name,
            ai_classifications=ai_classifications,
        )
        groups.append(group)

    return groups


def run_all_metrics(
    metric_ids: list[int],
    store: DataStore,
    brand_name: str = "",
    ai_classifications: Optional[dict] = None,
):
    """Run all requested metrics and return combined results.

    Args:
        metric_ids: List of metric IDs (1-100) to compute.
        store: DataStore with fetched GSC data.
        brand_name: Brand name for branded query detection.
        ai_classifications: AI classification cache.

    Returns:
        List of MetricResult objects.
    """
    from models.metric_result import MetricResult

    groups = get_metric_groups(
        metric_ids=metric_ids,
        store=store,
        brand_name=brand_name,
        ai_classifications=ai_classifications,
    )

    all_results: list[MetricResult] = []
    for group in groups:
        results = group.run_metrics(metric_ids)
        all_results.extend(results)

    return all_results
