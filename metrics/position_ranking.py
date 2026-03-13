"""Position & Ranking metrics (28-34).

Measures how rankings change over time (MoM / YoY drift), how stable
positions are across queries, gains and losses in top-3 positions,
improvement and degradation rates, and query cannibalization.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd

from metrics.base_metric import BaseMetricGroup
from models.metric_result import MetricResult, Severity, TrendDirection

logger = logging.getLogger(__name__)


class PositionRankingMetrics(BaseMetricGroup):
    """Metrics 28-34: Position & Ranking."""

    METRIC_REGISTRY: dict[int, str] = {
        28: "average_position_drift_mom",
        29: "average_position_drift_yoy",
        30: "rank_volatility_score",
        31: "top3_query_gain_loss_mom",
        32: "position_improvement_rate",
        33: "position_degradation_rate",
        34: "query_cannibalization_score",
    }

    # ------------------------------------------------------------------ #
    # 28 — Average Position Drift (MoM)
    # ------------------------------------------------------------------ #
    def average_position_drift_mom(self) -> MetricResult:
        """Change in average position per URL, current 30d vs previous 30d.

        Positive drift = positions got worse (higher number).
        Negative drift = positions improved (lower number).
        """
        df_90d = self.get_df("page_date_90d")
        df_30d = self.get_df("page_date_30d")

        if df_90d.empty or df_30d.empty:
            return self.create_result(
                metric_id=28,
                severity=Severity.INSIGHT,
                summary="Insufficient data to calculate MoM position drift.",
                recommendations=[
                    "Ensure at least 60 days of GSC data is available."
                ],
            )

        df_90d = df_90d.copy()
        df_30d = df_30d.copy()
        df_90d["date"] = pd.to_datetime(df_90d["date"])
        df_30d["date"] = pd.to_datetime(df_30d["date"])

        current_start = df_30d["date"].min()
        previous_start = current_start - pd.Timedelta(days=30)

        # Current period: weighted average position (weighted by impressions)
        current = self._weighted_avg_position(df_30d, "current_avg_pos")

        # Previous period from the 90d data
        prev_data = df_90d[
            (df_90d["date"] >= previous_start) & (df_90d["date"] < current_start)
        ]
        previous = self._weighted_avg_position(prev_data, "previous_avg_pos")

        if current.empty or previous.empty:
            return self.create_result(
                metric_id=28,
                severity=Severity.INSIGHT,
                summary="Not enough data in one or both periods to compute drift.",
                recommendations=["Wait for more data to accumulate."],
            )

        merged = current.merge(previous, on="page", how="inner")
        merged["drift"] = (
            merged["current_avg_pos"] - merged["previous_avg_pos"]
        ).round(2)

        if merged.empty:
            return self.create_result(
                metric_id=28,
                severity=Severity.INSIGHT,
                summary="No overlapping URLs found between the two periods.",
                recommendations=["Verify data completeness across both periods."],
            )

        site_avg_drift = merged["drift"].mean()

        # URLs that got worse (positive drift)
        worsened = merged[merged["drift"] > 1].sort_values(
            "drift", ascending=False
        )
        improved = merged[merged["drift"] < -1].sort_values("drift")

        # Severity: positive drift = rankings dropping
        if site_avg_drift > 3:
            severity = Severity.CRITICAL
            trend = TrendDirection.DECLINING
        elif site_avg_drift > 1.5:
            severity = Severity.HIGH
            trend = TrendDirection.DECLINING
        elif site_avg_drift > 0.5:
            severity = Severity.MEDIUM
            trend = TrendDirection.DECLINING
        elif site_avg_drift > -0.5:
            severity = Severity.LOW
            trend = TrendDirection.STABLE
        else:
            severity = Severity.INSIGHT
            trend = TrendDirection.IMPROVING

        table = pd.concat([worsened.head(15), improved.head(10)]).copy()
        table = table[["page", "previous_avg_pos", "current_avg_pos", "drift"]].rename(
            columns={
                "page": "URL",
                "previous_avg_pos": "Prev Avg Pos",
                "current_avg_pos": "Curr Avg Pos",
                "drift": "Drift",
            }
        )
        table["Prev Avg Pos"] = table["Prev Avg Pos"].round(1)
        table["Curr Avg Pos"] = table["Curr Avg Pos"].round(1)

        recommendations = []
        if len(worsened) > 0:
            recommendations.append(
                f"{len(worsened)} URLs drifted to worse positions (>1 pos). "
                "Check for content staleness, lost backlinks, or increased "
                "competition on those pages."
            )
        if len(improved) > 0:
            recommendations.append(
                f"{len(improved)} URLs improved their ranking (>1 pos). "
                "Identify what changed and replicate the approach."
            )
        if site_avg_drift > 1:
            recommendations.append(
                "Site-wide position regression detected. Cross-reference with "
                "Google algorithm update timelines and Search Console messages."
            )

        return self.create_result(
            metric_id=28,
            severity=severity,
            summary=(
                f"Average position drift MoM is {site_avg_drift:+.2f} positions. "
                f"{len(worsened)} URLs worsened (>1 pos), "
                f"{len(improved)} URLs improved (>1 pos)."
            ),
            computed_value=round(site_avg_drift, 2),
            affected_count=len(worsened),
            data_table=table,
            recommendations=recommendations,
            trend_direction=trend,
            benchmark_comparison=(
                "below" if site_avg_drift > 0.5 else
                "above" if site_avg_drift < -0.5 else "at"
            ),
        )

    # ------------------------------------------------------------------ #
    # 29 — Average Position Drift (YoY)
    # ------------------------------------------------------------------ #
    def average_position_drift_yoy(self) -> MetricResult:
        """Change in average position per URL, current 90d vs same 90d last year."""
        df_90d = self.get_df("page_date_90d")
        df_365d = self.get_df("page_date_365d")

        if df_90d.empty or df_365d.empty:
            return self.create_result(
                metric_id=29,
                severity=Severity.INSIGHT,
                summary="Insufficient data to calculate YoY position drift.",
                recommendations=[
                    "Ensure 365 days of GSC data is available for YoY analysis."
                ],
            )

        df_90d = df_90d.copy()
        df_365d = df_365d.copy()
        df_90d["date"] = pd.to_datetime(df_90d["date"])
        df_365d["date"] = pd.to_datetime(df_365d["date"])

        current_start = df_90d["date"].min()
        current_end = df_90d["date"].max()

        prev_start = current_start - pd.Timedelta(days=365)
        prev_end = current_end - pd.Timedelta(days=365)

        current = self._weighted_avg_position(df_90d, "current_avg_pos")

        prev_data = df_365d[
            (df_365d["date"] >= prev_start) & (df_365d["date"] <= prev_end)
        ]
        previous = self._weighted_avg_position(prev_data, "previous_avg_pos")

        if current.empty or previous.empty:
            return self.create_result(
                metric_id=29,
                severity=Severity.INSIGHT,
                summary="Not enough data in one or both year-over-year periods.",
                recommendations=[
                    "Ensure the GSC property has over 1 year of history."
                ],
            )

        merged = current.merge(previous, on="page", how="inner")
        merged["drift"] = (
            merged["current_avg_pos"] - merged["previous_avg_pos"]
        ).round(2)

        if merged.empty:
            return self.create_result(
                metric_id=29,
                severity=Severity.INSIGHT,
                summary="No overlapping URLs between this year and last year.",
                recommendations=["Verify that URLs have not changed significantly."],
            )

        site_avg_drift = merged["drift"].mean()

        worsened = merged[merged["drift"] > 2].sort_values(
            "drift", ascending=False
        )
        improved = merged[merged["drift"] < -2].sort_values("drift")

        if site_avg_drift > 5:
            severity = Severity.CRITICAL
            trend = TrendDirection.DECLINING
        elif site_avg_drift > 2:
            severity = Severity.HIGH
            trend = TrendDirection.DECLINING
        elif site_avg_drift > 0.5:
            severity = Severity.MEDIUM
            trend = TrendDirection.DECLINING
        elif site_avg_drift > -0.5:
            severity = Severity.LOW
            trend = TrendDirection.STABLE
        else:
            severity = Severity.INSIGHT
            trend = TrendDirection.IMPROVING

        table = pd.concat([worsened.head(15), improved.head(10)]).copy()
        table = table[["page", "previous_avg_pos", "current_avg_pos", "drift"]].rename(
            columns={
                "page": "URL",
                "previous_avg_pos": "Last Year Avg Pos",
                "current_avg_pos": "Current Avg Pos",
                "drift": "YoY Drift",
            }
        )
        table["Last Year Avg Pos"] = table["Last Year Avg Pos"].round(1)
        table["Current Avg Pos"] = table["Current Avg Pos"].round(1)

        recommendations = []
        if len(worsened) > 0:
            recommendations.append(
                f"{len(worsened)} URLs lost >2 positions YoY. Audit content "
                "freshness, competitive landscape changes, and backlink profiles "
                "for these pages."
            )
        if len(improved) > 0:
            recommendations.append(
                f"{len(improved)} URLs gained >2 positions YoY. Analyze what "
                "improvements were made and apply similar strategies elsewhere."
            )
        if site_avg_drift > 2:
            recommendations.append(
                "Significant year-over-year ranking regression. Compare with "
                "major algorithm updates and assess site-wide authority signals."
            )

        return self.create_result(
            metric_id=29,
            severity=severity,
            summary=(
                f"Average position drift YoY is {site_avg_drift:+.2f} positions. "
                f"{len(worsened)} URLs worsened (>2 pos), "
                f"{len(improved)} URLs improved (>2 pos)."
            ),
            computed_value=round(site_avg_drift, 2),
            affected_count=len(worsened),
            data_table=table,
            recommendations=recommendations,
            trend_direction=trend,
            benchmark_comparison=(
                "below" if site_avg_drift > 1 else
                "above" if site_avg_drift < -1 else "at"
            ),
        )

    # ------------------------------------------------------------------ #
    # 30 — Rank Volatility Score
    # ------------------------------------------------------------------ #
    def rank_volatility_score(self) -> MetricResult:
        """Standard deviation of positions across all query-date combos per URL.

        High volatility = unstable rankings. Low = consistent positions.
        """
        df = self.get_df("query_page_date_90d")

        if df.empty:
            return self.create_result(
                metric_id=30,
                severity=Severity.INSIGHT,
                summary="No query-page-date data available for volatility analysis.",
                recommendations=[
                    "Ensure query-page-date 90d data is fetched."
                ],
            )

        # Compute std dev of position for each page across all its
        # query-date combinations.  Only include pages with enough data
        # points for a meaningful std dev.
        page_stats = (
            df.groupby("page")
            .agg(
                position_std=("position", "std"),
                position_mean=("position", "mean"),
                data_points=("position", "count"),
                unique_queries=("query", "nunique"),
            )
            .reset_index()
        )

        # Require at least 5 data points for statistical reliability
        page_stats = page_stats[page_stats["data_points"] >= 5].copy()

        if page_stats.empty:
            return self.create_result(
                metric_id=30,
                severity=Severity.INSIGHT,
                summary="Not enough data points per URL to calculate volatility.",
                recommendations=[
                    "This metric needs at least 5 query-date data points per URL."
                ],
            )

        page_stats["position_std"] = page_stats["position_std"].round(2)
        page_stats["position_mean"] = page_stats["position_mean"].round(1)

        site_avg_volatility = page_stats["position_std"].mean()

        # High-volatility URLs
        high_vol_threshold = max(site_avg_volatility * 1.5, 5.0)
        high_vol = page_stats[
            page_stats["position_std"] > high_vol_threshold
        ].sort_values("position_std", ascending=False)

        # Low-volatility (stable) URLs for context
        low_vol = page_stats[
            page_stats["position_std"] < 2.0
        ].sort_values("position_std")

        if site_avg_volatility > 10:
            severity = Severity.HIGH
        elif site_avg_volatility > 6:
            severity = Severity.MEDIUM
        elif site_avg_volatility > 3:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        table = pd.concat([high_vol.head(20), low_vol.head(5)]).copy()
        table = table[
            ["page", "position_mean", "position_std", "unique_queries", "data_points"]
        ].rename(
            columns={
                "page": "URL",
                "position_mean": "Avg Position",
                "position_std": "Volatility (Std Dev)",
                "unique_queries": "Unique Queries",
                "data_points": "Data Points",
            }
        )

        recommendations = []
        if len(high_vol) > 0:
            recommendations.append(
                f"{len(high_vol)} URLs have high rank volatility "
                f"(std dev > {high_vol_threshold:.1f}). These pages may be "
                "affected by thin content, keyword cannibalization, or "
                "fluctuating search intent. Strengthen topical authority "
                "and improve content depth."
            )
        if site_avg_volatility > 5:
            recommendations.append(
                "Site-wide volatility is elevated. Consider auditing "
                "internal linking structure, consolidating similar content, "
                "and building more authoritative backlinks."
            )
        recommendations.append(
            "Stable rankings (low volatility) indicate strong topical "
            "relevance. Use those pages as models for improving volatile ones."
        )

        return self.create_result(
            metric_id=30,
            severity=severity,
            summary=(
                f"Average rank volatility across the site is {site_avg_volatility:.2f} "
                f"(std dev of position). {len(high_vol)} URLs show high volatility, "
                f"{len(low_vol)} are highly stable."
            ),
            computed_value=round(site_avg_volatility, 2),
            affected_count=len(high_vol),
            data_table=table,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------ #
    # 31 — Top-3 Query Gain/Loss Count (MoM)
    # ------------------------------------------------------------------ #
    def top3_query_gain_loss_mom(self) -> MetricResult:
        """Net change in the number of queries ranking in top 3 positions, MoM."""
        df = self.get_df("query_page_date_90d")

        if df.empty:
            return self.create_result(
                metric_id=31,
                severity=Severity.INSIGHT,
                summary="No query-page-date data available for top-3 analysis.",
                recommendations=[
                    "Ensure query-page-date 90d data is fetched."
                ],
            )

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])

        max_date = df["date"].max()
        split_date = max_date - pd.Timedelta(days=30)

        current = df[df["date"] > split_date]
        previous = df[(df["date"] <= split_date) & (df["date"] > split_date - pd.Timedelta(days=30))]

        if current.empty or previous.empty:
            return self.create_result(
                metric_id=31,
                severity=Severity.INSIGHT,
                summary="Not enough data in both 30-day periods for comparison.",
                recommendations=["Ensure at least 60 days of data is available."],
            )

        # For each page, find queries that had avg position <= 3
        def get_top3_queries(period_df: pd.DataFrame) -> pd.DataFrame:
            avg_pos = (
                period_df.groupby(["page", "query"], as_index=False)["position"]
                .mean()
            )
            return avg_pos[avg_pos["position"] <= 3]

        current_top3 = get_top3_queries(current)
        previous_top3 = get_top3_queries(previous)

        # Per-page gain/loss
        current_counts = (
            current_top3.groupby("page", as_index=False)["query"]
            .nunique()
            .rename(columns={"query": "current_top3"})
        )
        previous_counts = (
            previous_top3.groupby("page", as_index=False)["query"]
            .nunique()
            .rename(columns={"query": "previous_top3"})
        )

        merged = current_counts.merge(previous_counts, on="page", how="outer").fillna(0)
        merged["current_top3"] = merged["current_top3"].astype(int)
        merged["previous_top3"] = merged["previous_top3"].astype(int)
        merged["net_change"] = merged["current_top3"] - merged["previous_top3"]

        site_total_current = merged["current_top3"].sum()
        site_total_previous = merged["previous_top3"].sum()
        site_net = site_total_current - site_total_previous

        # Identify specific gained and lost queries
        current_set = set(
            zip(current_top3["page"], current_top3["query"])
        )
        previous_set = set(
            zip(previous_top3["page"], previous_top3["query"])
        )
        gained_pairs = current_set - previous_set
        lost_pairs = previous_set - current_set

        gainers = merged[merged["net_change"] > 0].sort_values(
            "net_change", ascending=False
        )
        losers = merged[merged["net_change"] < 0].sort_values("net_change")

        if site_net < -10:
            severity = Severity.CRITICAL
            trend = TrendDirection.DECLINING
        elif site_net < -3:
            severity = Severity.HIGH
            trend = TrendDirection.DECLINING
        elif site_net < 0:
            severity = Severity.MEDIUM
            trend = TrendDirection.DECLINING
        elif site_net == 0:
            severity = Severity.LOW
            trend = TrendDirection.STABLE
        else:
            severity = Severity.INSIGHT
            trend = TrendDirection.IMPROVING

        # Build table showing URLs with gains/losses
        table = pd.concat([losers.head(15), gainers.head(10)]).copy()
        table = table[
            ["page", "previous_top3", "current_top3", "net_change"]
        ].rename(
            columns={
                "page": "URL",
                "previous_top3": "Prev Top-3 Queries",
                "current_top3": "Curr Top-3 Queries",
                "net_change": "Net Change",
            }
        )

        recommendations = []
        if len(lost_pairs) > 0:
            recommendations.append(
                f"{len(lost_pairs)} query-page combinations dropped out of the "
                "top 3. Review these pages for content freshness, SERP feature "
                "changes, and competitor activity."
            )
        if len(gained_pairs) > 0:
            recommendations.append(
                f"{len(gained_pairs)} query-page combinations entered the top 3. "
                "Capitalize on this momentum with internal linking and CTR "
                "optimization (title tag and meta description refinement)."
            )
        if site_net < 0:
            recommendations.append(
                "Net loss in top-3 positions. Prioritize pages that dropped "
                "from position 1-3 to 4-10 — these are the quickest wins "
                "to recover."
            )

        return self.create_result(
            metric_id=31,
            severity=severity,
            summary=(
                f"Net top-3 query change MoM: {site_net:+d} "
                f"({site_total_current} current vs {site_total_previous} previous). "
                f"{len(gained_pairs)} gained, {len(lost_pairs)} lost."
            ),
            computed_value=float(site_net),
            affected_count=len(lost_pairs),
            data_table=table,
            recommendations=recommendations,
            trend_direction=trend,
        )

    # ------------------------------------------------------------------ #
    # 32 — Position Improvement Rate
    # ------------------------------------------------------------------ #
    def position_improvement_rate(self) -> MetricResult:
        """Percent of each URL's queries that improved in position MoM."""
        df = self.get_df("query_page_date_90d")

        if df.empty:
            return self.create_result(
                metric_id=32,
                severity=Severity.INSIGHT,
                summary="No query-page-date data available for improvement analysis.",
                recommendations=[
                    "Ensure query-page-date 90d data is fetched."
                ],
            )

        improvement_data = self._compute_query_position_changes(df)

        if improvement_data.empty:
            return self.create_result(
                metric_id=32,
                severity=Severity.INSIGHT,
                summary="Not enough overlapping query data between periods.",
                recommendations=["Wait for more data to accumulate."],
            )

        # Aggregate per page
        page_rates = (
            improvement_data.groupby("page")
            .agg(
                total_queries=("query", "count"),
                improved_queries=("improved", "sum"),
            )
            .reset_index()
        )
        page_rates["improvement_rate"] = (
            page_rates["improved_queries"] / page_rates["total_queries"] * 100
        ).round(1)

        site_avg_rate = page_rates["improvement_rate"].mean()

        # Low improvement rate = stagnation
        low_improvement = page_rates[
            (page_rates["improvement_rate"] < 20) & (page_rates["total_queries"] >= 3)
        ].sort_values("improvement_rate")

        high_improvement = page_rates[
            page_rates["improvement_rate"] > 60
        ].sort_values("improvement_rate", ascending=False)

        if site_avg_rate < 20:
            severity = Severity.HIGH
        elif site_avg_rate < 35:
            severity = Severity.MEDIUM
        elif site_avg_rate < 50:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        table = pd.concat([low_improvement.head(15), high_improvement.head(10)]).copy()
        table = table[
            ["page", "total_queries", "improved_queries", "improvement_rate"]
        ].rename(
            columns={
                "page": "URL",
                "total_queries": "Total Queries",
                "improved_queries": "Improved Queries",
                "improvement_rate": "Improvement Rate %",
            }
        )

        recommendations = []
        if len(low_improvement) > 0:
            recommendations.append(
                f"{len(low_improvement)} URLs have a position improvement rate "
                "below 20%. These pages are stagnating — consider content "
                "refreshes, new internal links, and backlink acquisition."
            )
        if site_avg_rate < 30:
            recommendations.append(
                "Site-wide improvement rate is low. Focus on updating aging "
                "content, improving E-E-A-T signals, and targeting "
                "striking-distance keywords (positions 4-20)."
            )
        recommendations.append(
            "Pages with high improvement rates reveal what is working. "
            "Analyze their recent changes and apply those patterns broadly."
        )

        trend = (
            TrendDirection.IMPROVING if site_avg_rate > 50
            else TrendDirection.DECLINING if site_avg_rate < 25
            else TrendDirection.STABLE
        )

        return self.create_result(
            metric_id=32,
            severity=severity,
            summary=(
                f"Average position improvement rate is {site_avg_rate:.1f}%. "
                f"{len(low_improvement)} URLs have stagnant rankings (<20% improved), "
                f"{len(high_improvement)} URLs are strongly improving (>60%)."
            ),
            computed_value=round(site_avg_rate, 2),
            affected_count=len(low_improvement),
            data_table=table,
            recommendations=recommendations,
            trend_direction=trend,
        )

    # ------------------------------------------------------------------ #
    # 33 — Position Degradation Rate
    # ------------------------------------------------------------------ #
    def position_degradation_rate(self) -> MetricResult:
        """Percent of each URL's queries that degraded in position MoM."""
        df = self.get_df("query_page_date_90d")

        if df.empty:
            return self.create_result(
                metric_id=33,
                severity=Severity.INSIGHT,
                summary="No query-page-date data available for degradation analysis.",
                recommendations=[
                    "Ensure query-page-date 90d data is fetched."
                ],
            )

        change_data = self._compute_query_position_changes(df)

        if change_data.empty:
            return self.create_result(
                metric_id=33,
                severity=Severity.INSIGHT,
                summary="Not enough overlapping query data between periods.",
                recommendations=["Wait for more data to accumulate."],
            )

        # Aggregate per page
        page_rates = (
            change_data.groupby("page")
            .agg(
                total_queries=("query", "count"),
                degraded_queries=("degraded", "sum"),
            )
            .reset_index()
        )
        page_rates["degradation_rate"] = (
            page_rates["degraded_queries"] / page_rates["total_queries"] * 100
        ).round(1)

        site_avg_rate = page_rates["degradation_rate"].mean()

        high_degradation = page_rates[
            (page_rates["degradation_rate"] > 50) & (page_rates["total_queries"] >= 3)
        ].sort_values("degradation_rate", ascending=False)

        low_degradation = page_rates[
            page_rates["degradation_rate"] < 15
        ].sort_values("degradation_rate")

        if site_avg_rate > 60:
            severity = Severity.CRITICAL
        elif site_avg_rate > 45:
            severity = Severity.HIGH
        elif site_avg_rate > 30:
            severity = Severity.MEDIUM
        elif site_avg_rate > 15:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        table = pd.concat(
            [high_degradation.head(20), low_degradation.head(5)]
        ).copy()
        table = table[
            ["page", "total_queries", "degraded_queries", "degradation_rate"]
        ].rename(
            columns={
                "page": "URL",
                "total_queries": "Total Queries",
                "degraded_queries": "Degraded Queries",
                "degradation_rate": "Degradation Rate %",
            }
        )

        recommendations = []
        if len(high_degradation) > 0:
            recommendations.append(
                f"{len(high_degradation)} URLs have a degradation rate above 50%. "
                "These pages are actively losing ground. Prioritize them for "
                "content updates, technical fixes, and competitive analysis."
            )
        if site_avg_rate > 40:
            recommendations.append(
                "Site-wide degradation rate is alarmingly high. Check for "
                "technical SEO issues (slow load times, crawl errors), "
                "content quality problems, or manual actions in Search Console."
            )
        recommendations.append(
            "Cross-reference degrading queries with SERP feature changes — "
            "a featured snippet or People Also Ask box may be displacing "
            "your organic position."
        )

        trend = (
            TrendDirection.DECLINING if site_avg_rate > 40
            else TrendDirection.STABLE if site_avg_rate > 20
            else TrendDirection.IMPROVING
        )

        return self.create_result(
            metric_id=33,
            severity=severity,
            summary=(
                f"Average position degradation rate is {site_avg_rate:.1f}%. "
                f"{len(high_degradation)} URLs have >50% of queries dropping, "
                f"{len(low_degradation)} URLs are holding steady (<15%)."
            ),
            computed_value=round(site_avg_rate, 2),
            affected_count=len(high_degradation),
            data_table=table,
            recommendations=recommendations,
            trend_direction=trend,
        )

    # ------------------------------------------------------------------ #
    # 34 — Query Cannibalization Score
    # ------------------------------------------------------------------ #
    def query_cannibalization_score(self) -> MetricResult:
        """Count of queries where multiple URLs compete for the same term.

        Queries that appear with 2+ distinct pages indicate potential
        keyword cannibalization, which can dilute ranking signals.
        """
        df_90d = self.get_df("query_page_90d")
        df_365d = self.get_df("query_page_365d")

        # Use 90d as primary; merge with 365d for broader detection
        if df_90d.empty:
            return self.create_result(
                metric_id=34,
                severity=Severity.INSIGHT,
                summary="No query-page data available for cannibalization analysis.",
                recommendations=[
                    "Ensure query-page 90d data is fetched."
                ],
            )

        df = df_90d.copy()

        # Optionally incorporate 365d data for historical cannibalization
        if not df_365d.empty:
            # Add any query-page combos from 365d that are not in 90d
            combined = pd.concat([df, df_365d]).drop_duplicates(
                subset=["query", "page"], keep="first"
            )
        else:
            combined = df

        # Count distinct pages per query
        query_pages = (
            combined.groupby("query")
            .agg(
                page_count=("page", "nunique"),
                total_impressions=("impressions", "sum"),
            )
            .reset_index()
        )

        cannibalizing = query_pages[query_pages["page_count"] >= 2].sort_values(
            "total_impressions", ascending=False
        )

        total_queries = len(query_pages)
        cannibalization_count = len(cannibalizing)
        cannibalization_rate = (
            cannibalization_count / max(total_queries, 1) * 100
        )

        if cannibalization_count == 0:
            return self.create_result(
                metric_id=34,
                severity=Severity.INSIGHT,
                summary="No query cannibalization detected — each query maps to a single URL.",
                computed_value=0.0,
                affected_count=0,
                recommendations=[
                    "Continue maintaining clear topical focus per URL."
                ],
            )

        # Build detailed data table: query, competing pages, positions
        detail_rows = []
        for _, row in cannibalizing.head(50).iterrows():
            query = row["query"]
            pages_for_query = combined[combined["query"] == query].copy()
            pages_for_query = pages_for_query.sort_values("impressions", ascending=False)
            for _, p_row in pages_for_query.iterrows():
                detail_rows.append(
                    {
                        "Query": query,
                        "URL": p_row["page"],
                        "Impressions": int(p_row["impressions"]),
                        "Clicks": int(p_row.get("clicks", 0)),
                        "Avg Position": round(p_row.get("position", 0), 1),
                    }
                )

        detail_table = pd.DataFrame(detail_rows).head(25)

        if cannibalization_rate > 40:
            severity = Severity.CRITICAL
        elif cannibalization_rate > 25:
            severity = Severity.HIGH
        elif cannibalization_rate > 15:
            severity = Severity.MEDIUM
        elif cannibalization_rate > 5:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        # Top cannibalizing queries by impression volume
        top_cannib_impressions = cannibalizing["total_impressions"].sum()

        recommendations = [
            f"{cannibalization_count} queries ({cannibalization_rate:.1f}%) "
            "are served by multiple URLs. For each cannibalizing query, "
            "designate one canonical target page and redirect or "
            "de-optimize the competing pages.",
            "Review the top-impression cannibalizing queries first — "
            "consolidating those will have the biggest impact.",
            "Use internal linking to signal which page should rank for "
            "each query. Add canonical tags if pages serve similar content.",
        ]
        if cannibalization_rate > 20:
            recommendations.append(
                "High cannibalization rate suggests a content architecture "
                "problem. Consider building a topic cluster model with clear "
                "pillar pages and supporting articles."
            )

        return self.create_result(
            metric_id=34,
            severity=severity,
            summary=(
                f"{cannibalization_count} queries ({cannibalization_rate:.1f}%) "
                f"are competing across multiple URLs, affecting "
                f"{top_cannib_impressions:,.0f} total impressions."
            ),
            computed_value=round(cannibalization_rate, 2),
            affected_count=cannibalization_count,
            data_table=detail_table,
            recommendations=recommendations,
            details={
                "total_queries": total_queries,
                "cannibalizing_queries": cannibalization_count,
                "cannibalization_rate_pct": round(cannibalization_rate, 2),
            },
        )

    # ================================================================== #
    # Helper methods
    # ================================================================== #

    @staticmethod
    def _weighted_avg_position(
        df: pd.DataFrame, col_name: str
    ) -> pd.DataFrame:
        """Compute impression-weighted average position per page.

        Returns a DataFrame with columns [page, <col_name>].
        """
        if df.empty:
            return pd.DataFrame(columns=["page", col_name])

        # Weighted average: sum(position * impressions) / sum(impressions)
        weighted = df.copy()
        weighted["weighted_pos"] = weighted["position"] * weighted["impressions"]

        agg = weighted.groupby("page", as_index=False).agg(
            total_weighted=("weighted_pos", "sum"),
            total_impressions=("impressions", "sum"),
        )
        agg = agg[agg["total_impressions"] > 0].copy()
        agg[col_name] = (agg["total_weighted"] / agg["total_impressions"]).round(2)

        return agg[["page", col_name]]

    @staticmethod
    def _compute_query_position_changes(df: pd.DataFrame) -> pd.DataFrame:
        """Compare average position per query-page between current and previous 30d.

        Returns DataFrame with columns:
            page, query, current_avg_pos, previous_avg_pos, change, improved, degraded
        """
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])

        max_date = df["date"].max()
        split_date = max_date - pd.Timedelta(days=30)

        current = df[df["date"] > split_date]
        previous = df[
            (df["date"] <= split_date)
            & (df["date"] > split_date - pd.Timedelta(days=30))
        ]

        if current.empty or previous.empty:
            return pd.DataFrame()

        current_avg = (
            current.groupby(["page", "query"], as_index=False)["position"].mean()
        ).rename(columns={"position": "current_avg_pos"})

        previous_avg = (
            previous.groupby(["page", "query"], as_index=False)["position"].mean()
        ).rename(columns={"position": "previous_avg_pos"})

        merged = current_avg.merge(previous_avg, on=["page", "query"], how="inner")

        # Negative change = improvement (lower position number is better)
        merged["change"] = merged["current_avg_pos"] - merged["previous_avg_pos"]
        merged["improved"] = merged["change"] < -0.5  # At least half a position
        merged["degraded"] = merged["change"] > 0.5

        return merged
