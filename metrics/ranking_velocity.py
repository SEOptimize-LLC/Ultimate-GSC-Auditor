"""Ranking Velocity & Momentum metrics (78-84).

Analyzes the speed and direction of ranking changes, identifying
fast-moving queries, stabilization patterns, recovery behavior,
and proximity to page 1 threshold.
"""

import logging
from datetime import timedelta

import numpy as np
import pandas as pd

from metrics.base_metric import BaseMetricGroup
from models.metric_result import MetricResult, Severity, TrendDirection

logger = logging.getLogger(__name__)


class RankingVelocityMetrics(BaseMetricGroup):
    """Metrics 78-84: Ranking Velocity & Momentum analysis."""

    METRIC_REGISTRY: dict[int, str] = {
        78: "metric_ranking_velocity_score",
        79: "metric_query_acceleration_rate",
        80: "metric_position_stabilization_rate",
        81: "metric_fast_rising_query_count",
        82: "metric_fast_falling_query_count",
        83: "metric_rank_recovery_speed",
        84: "metric_position_11_proximity_rate",
    }

    # ------------------------------------------------------------------ #
    # Metric 78 — Ranking Velocity Score
    # ------------------------------------------------------------------ #
    def metric_ranking_velocity_score(self) -> MetricResult:
        """Impression-weighted average linear slope of position over time per query-page pair.

        Negative velocity = positions improving (moving toward 1).
        Positive velocity = positions declining (moving toward higher numbers).
        """
        df = self.get_df("query_page_date_90d")
        if df.empty:
            return self._error_result(78, "No query-page-date data available")

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])

        # Assign a numeric day index for regression
        min_date = df["date"].min()
        df["day_index"] = (df["date"] - min_date).dt.days

        # Compute linear slope per query-page pair (need at least 3 data points)
        pair_counts = df.groupby(["query", "page"]).size()
        valid_pairs = pair_counts[pair_counts >= 3].index
        df_valid = df.set_index(["query", "page"]).loc[valid_pairs].reset_index()

        if df_valid.empty:
            return self._error_result(
                78, "Not enough temporal data points per query-page pair (need 3+)"
            )

        def compute_slope(group: pd.DataFrame) -> pd.Series:
            x = group["day_index"].values.astype(float)
            y = group["position"].values.astype(float)
            total_imps = group["impressions"].sum()
            if len(x) < 3 or np.std(x) == 0:
                return pd.Series({"slope": 0.0, "total_impressions": total_imps})
            coeffs = np.polyfit(x, y, 1)
            return pd.Series({"slope": coeffs[0], "total_impressions": total_imps})

        slopes = (
            df_valid.groupby(["query", "page"])
            .apply(compute_slope)
            .reset_index()
        )

        total_impressions = slopes["total_impressions"].sum()
        if total_impressions == 0:
            return self._error_result(78, "No impressions for velocity calculation")

        # Impression-weighted average velocity
        slopes["weighted_slope"] = slopes["slope"] * slopes["total_impressions"]
        avg_velocity = slopes["weighted_slope"].sum() / total_impressions

        # Classify pairs
        improving = slopes[slopes["slope"] < -0.02]
        declining = slopes[slopes["slope"] > 0.02]
        stable = slopes[(slopes["slope"] >= -0.02) & (slopes["slope"] <= 0.02)]

        total_pairs = len(slopes)
        improving_count = len(improving)
        declining_count = len(declining)
        stable_count = len(stable)

        # Positive avg velocity means rankings are declining on average
        if avg_velocity > 0:
            severity = Severity.HIGH
        elif avg_velocity > -0.01:
            severity = Severity.MEDIUM
        elif avg_velocity > -0.05:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        trend = (
            TrendDirection.IMPROVING
            if avg_velocity < -0.02
            else TrendDirection.DECLINING
            if avg_velocity > 0.02
            else TrendDirection.STABLE
        )

        direction_label = "declining" if avg_velocity > 0 else "improving"
        summary = (
            f"Impression-weighted ranking velocity is {avg_velocity:+.4f} positions/day "
            f"(rankings are {direction_label} on average). "
            f"Of {total_pairs:,} query-page pairs: {improving_count:,} improving, "
            f"{declining_count:,} declining, {stable_count:,} stable. "
            f"{'Positive velocity means rankings are moving backward — investigate causes.' if avg_velocity > 0 else 'Negative velocity indicates healthy ranking momentum.'}"
        )

        # Show top declining pairs (biggest positive slopes = worst declines)
        display_df = (
            slopes
            .sort_values("slope", ascending=False)
            [["query", "page", "slope", "total_impressions"]]
            .head(25)
            .copy()
        )
        display_df["slope"] = display_df["slope"].round(4)
        display_df.rename(columns={
            "slope": "velocity_per_day",
            "total_impressions": "impressions",
        }, inplace=True)

        recommendations = []
        if avg_velocity > 0:
            recommendations.extend([
                "Investigate query-page pairs with the highest positive velocity (fastest declines) for ranking drops.",
                "Check for algorithm updates, competitor content improvements, or technical issues causing decline.",
                "Prioritize content refreshes and link building for declining high-impression query-page pairs.",
                "Monitor Core Web Vitals and mobile usability as potential contributors to ranking declines.",
            ])
        else:
            recommendations.extend([
                "Ranking momentum is positive. Maintain content freshness and link velocity for sustained improvement.",
                "Identify the fastest-improving query-page pairs and replicate their optimization patterns across the site.",
            ])

        return self.create_result(
            metric_id=78,
            severity=severity,
            summary=summary,
            computed_value=round(avg_velocity, 4),
            affected_count=declining_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            trend_direction=trend,
            details={
                "avg_velocity": round(avg_velocity, 4),
                "total_pairs": total_pairs,
                "improving_pairs": improving_count,
                "declining_pairs": declining_count,
                "stable_pairs": stable_count,
                "total_weighted_impressions": int(total_impressions),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 79 — Query Acceleration Rate
    # ------------------------------------------------------------------ #
    def metric_query_acceleration_rate(self) -> MetricResult:
        """Compare position change rate in last 15d vs previous 15d within 30d data.

        Acceleration = position improving faster recently than before.
        """
        df_90d = self.get_df("query_date_90d")
        df_30d = self.get_df("query_date_30d")

        # Prefer 30d data; fall back to last 30d of 90d data
        if not df_30d.empty:
            df = df_30d.copy()
        elif not df_90d.empty:
            df = df_90d.copy()
            df["date"] = pd.to_datetime(df["date"])
            max_date = df["date"].max()
            df = df[df["date"] >= max_date - timedelta(days=29)]
        else:
            return self._error_result(79, "No query-date data available")

        df["date"] = pd.to_datetime(df["date"])
        max_date = df["date"].max()
        mid_date = max_date - timedelta(days=14)

        # Split into two 15-day halves
        recent = df[df["date"] > mid_date]
        earlier = df[df["date"] <= mid_date]

        if recent.empty or earlier.empty:
            return self._error_result(79, "Insufficient data to split into two 15-day periods")

        # Average position per query in each half
        recent_avg = (
            recent.groupby("query")
            .agg(recent_pos=("position", "mean"), recent_imps=("impressions", "sum"))
            .reset_index()
        )
        earlier_avg = (
            earlier.groupby("query")
            .agg(earlier_pos=("position", "mean"), earlier_imps=("impressions", "sum"))
            .reset_index()
        )

        merged = recent_avg.merge(earlier_avg, on="query", how="inner")
        if merged.empty:
            return self._error_result(79, "No queries found in both 15-day periods")

        # Position change: negative = improving (position number decreasing)
        merged["pos_change"] = merged["recent_pos"] - merged["earlier_pos"]
        merged["total_imps"] = merged["recent_imps"] + merged["earlier_imps"]

        # Classify acceleration
        accelerating = merged[merged["pos_change"] < -0.5]  # improving faster
        decelerating = merged[merged["pos_change"] > 0.5]   # declining
        neutral = merged[(merged["pos_change"] >= -0.5) & (merged["pos_change"] <= 0.5)]

        total_queries = len(merged)
        accel_count = len(accelerating)
        decel_count = len(decelerating)
        accel_pct = (accel_count / total_queries * 100) if total_queries > 0 else 0.0
        decel_pct = (decel_count / total_queries * 100) if total_queries > 0 else 0.0

        # Net acceleration score
        net_accel_pct = accel_pct - decel_pct

        if net_accel_pct < -20:
            severity = Severity.HIGH
        elif net_accel_pct < -5:
            severity = Severity.MEDIUM
        elif net_accel_pct < 5:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        trend = (
            TrendDirection.IMPROVING
            if net_accel_pct > 5
            else TrendDirection.DECLINING
            if net_accel_pct < -5
            else TrendDirection.STABLE
        )

        summary = (
            f"Query acceleration rate: {accel_pct:.1f}% of queries are accelerating "
            f"(improving faster recently), {decel_pct:.1f}% are decelerating. "
            f"Net acceleration: {net_accel_pct:+.1f}%. "
            f"{accel_count:,} accelerating vs {decel_count:,} decelerating out of "
            f"{total_queries:,} total queries. "
            f"{'Positive net acceleration indicates strengthening ranking momentum.' if net_accel_pct > 0 else 'Negative net acceleration suggests ranking momentum is slowing or reversing.'}"
        )

        # Show top accelerating queries
        display_df = (
            accelerating
            .sort_values("pos_change", ascending=True)
            [["query", "earlier_pos", "recent_pos", "pos_change", "total_imps"]]
            .head(25)
            .copy()
        )
        if not display_df.empty:
            display_df["earlier_pos"] = display_df["earlier_pos"].round(1)
            display_df["recent_pos"] = display_df["recent_pos"].round(1)
            display_df["pos_change"] = display_df["pos_change"].round(2)
            display_df.rename(columns={
                "earlier_pos": "prev_15d_pos",
                "recent_pos": "last_15d_pos",
                "total_imps": "impressions",
            }, inplace=True)

        recommendations = []
        if net_accel_pct < -5:
            recommendations.extend([
                "Investigate decelerating queries for content staleness, competitor gains, or technical issues.",
                "Focus content refresh efforts on high-impression queries showing deceleration.",
                "Check for recent algorithm updates that may have shifted ranking factors.",
                "Strengthen internal linking to pages associated with decelerating queries.",
            ])
        else:
            recommendations.extend([
                "Positive acceleration indicates effective SEO efforts. Maintain current optimization strategies.",
                "Double down on content and link building for accelerating queries to sustain momentum.",
            ])

        return self.create_result(
            metric_id=79,
            severity=severity,
            summary=summary,
            computed_value=round(net_accel_pct, 2),
            affected_count=accel_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            trend_direction=trend,
            details={
                "accelerating_queries": accel_count,
                "decelerating_queries": decel_count,
                "neutral_queries": len(neutral),
                "total_queries": total_queries,
                "accel_pct": round(accel_pct, 2),
                "decel_pct": round(decel_pct, 2),
                "net_acceleration": round(net_accel_pct, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 80 — Position Stabilization Rate
    # ------------------------------------------------------------------ #
    def metric_position_stabilization_rate(self) -> MetricResult:
        """Percentage of query-page pairs with position std dev < 1.0 over 90 days."""
        df = self.get_df("query_page_date_90d")
        if df.empty:
            return self._error_result(80, "No query-page-date data available")

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])

        # Need at least 3 data points per pair for meaningful std dev
        pair_counts = df.groupby(["query", "page"]).size()
        valid_pairs = pair_counts[pair_counts >= 3].index

        if len(valid_pairs) == 0:
            return self._error_result(
                80, "Not enough temporal data points per query-page pair (need 3+)"
            )

        df_valid = df.set_index(["query", "page"]).loc[valid_pairs].reset_index()

        pair_stats = (
            df_valid.groupby(["query", "page"])
            .agg(
                pos_std=("position", "std"),
                pos_mean=("position", "mean"),
                total_impressions=("impressions", "sum"),
                data_points=("date", "count"),
            )
            .reset_index()
        )

        stable_pairs = pair_stats[pair_stats["pos_std"] < 1.0]
        volatile_pairs = pair_stats[pair_stats["pos_std"] >= 1.0]
        total_pairs = len(pair_stats)
        stable_count = len(stable_pairs)
        volatile_count = len(volatile_pairs)
        stable_pct = (stable_count / total_pairs * 100) if total_pairs > 0 else 0.0

        avg_std = pair_stats["pos_std"].mean()

        if stable_pct < 30:
            severity = Severity.LOW
        elif stable_pct < 50:
            severity = Severity.MEDIUM
        elif stable_pct < 70:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{stable_count:,} of {total_pairs:,} query-page pairs ({stable_pct:.1f}%) "
            f"have stable positions (std dev < 1.0). "
            f"{volatile_count:,} pairs show significant position volatility. "
            f"Average position std dev across all pairs: {avg_std:.2f}. "
            f"{'Low stabilization suggests volatile rankings — investigate root causes.' if stable_pct < 30 else 'Good position stability indicates consistent ranking signals.'}"
        )

        # Show most volatile pairs
        display_df = (
            volatile_pairs
            .sort_values("pos_std", ascending=False)
            [["query", "page", "pos_std", "pos_mean", "total_impressions", "data_points"]]
            .head(25)
            .copy()
        )
        if not display_df.empty:
            display_df["pos_std"] = display_df["pos_std"].round(2)
            display_df["pos_mean"] = display_df["pos_mean"].round(1)
            display_df.rename(columns={
                "pos_std": "position_std_dev",
                "pos_mean": "avg_position",
                "total_impressions": "impressions",
            }, inplace=True)

        recommendations = []
        if stable_pct < 50:
            recommendations.extend([
                "Investigate highly volatile query-page pairs for thin content, keyword cannibalization, or weak link profiles.",
                "Strengthen on-page relevance signals (headings, content depth) for volatile queries to anchor rankings.",
                "Check for multiple pages competing for the same query — consolidate content to reduce internal competition.",
                "Improve site-wide authority through quality link building to reduce ranking fluctuations.",
            ])
        else:
            recommendations.extend([
                "Ranking stability is healthy. Monitor volatile pairs for early signs of declining rankings.",
                "Continue maintaining content quality and backlink profiles to sustain stable positions.",
            ])

        return self.create_result(
            metric_id=80,
            severity=severity,
            summary=summary,
            computed_value=round(stable_pct, 2),
            affected_count=volatile_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "stable_pairs": stable_count,
                "volatile_pairs": volatile_count,
                "total_pairs": total_pairs,
                "stable_pct": round(stable_pct, 2),
                "avg_position_std": round(avg_std, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 81 — Fast-Rising Query Count
    # ------------------------------------------------------------------ #
    def metric_fast_rising_query_count(self) -> MetricResult:
        """Queries that improved position by > 5 spots in last 30d vs previous 30d."""
        df = self.get_df("query_page_date_90d")
        if df.empty:
            return self._error_result(81, "No query-page-date data available")

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])

        max_date = df["date"].max()
        current_start = max_date - timedelta(days=29)
        prev_start = max_date - timedelta(days=59)
        prev_end = max_date - timedelta(days=30)

        # Average position per query in each period
        current = (
            df[df["date"] >= current_start]
            .groupby("query")
            .agg(curr_pos=("position", "mean"), curr_imps=("impressions", "sum"))
            .reset_index()
        )
        previous = (
            df[(df["date"] >= prev_start) & (df["date"] <= prev_end)]
            .groupby("query")
            .agg(prev_pos=("position", "mean"), prev_imps=("impressions", "sum"))
            .reset_index()
        )

        merged = current.merge(previous, on="query", how="inner")
        if merged.empty:
            return self._error_result(81, "No queries found in both 30-day periods")

        # Position improvement: positive change means position number decreased (improved)
        merged["pos_change"] = merged["prev_pos"] - merged["curr_pos"]
        merged["total_imps"] = merged["curr_imps"] + merged["prev_imps"]

        fast_rising = merged[merged["pos_change"] > 5.0].sort_values(
            "pos_change", ascending=False
        )
        fast_rising_count = len(fast_rising)
        total_queries = len(merged)

        severity = Severity.INSIGHT

        summary = (
            f"{fast_rising_count:,} queries improved by more than 5 positions "
            f"in the last 30 days compared to the previous 30 days "
            f"(out of {total_queries:,} total queries with data in both periods). "
            f"{'These fast risers indicate strong momentum — capitalize on this trend.' if fast_rising_count > 0 else 'No queries showed rapid ranking improvement in this period.'}"
        )

        # Show top risers
        display_df = (
            fast_rising
            [["query", "prev_pos", "curr_pos", "pos_change", "total_imps"]]
            .head(25)
            .copy()
        )
        if not display_df.empty:
            display_df["prev_pos"] = display_df["prev_pos"].round(1)
            display_df["curr_pos"] = display_df["curr_pos"].round(1)
            display_df["pos_change"] = display_df["pos_change"].round(1)
            display_df.rename(columns={
                "prev_pos": "prev_30d_pos",
                "curr_pos": "last_30d_pos",
                "pos_change": "improvement",
                "total_imps": "impressions",
            }, inplace=True)

        recommendations = [
            "Strengthen content and link profiles for fast-rising queries to sustain upward momentum.",
            "Add internal links from high-authority pages to URLs ranking for these rising queries.",
            "Analyze what caused these queries to rise — replicate the pattern for other underperforming queries.",
            "Monitor fast risers closely; rapid gains can reverse if the underlying signals weaken.",
        ]

        return self.create_result(
            metric_id=81,
            severity=severity,
            summary=summary,
            computed_value=float(fast_rising_count),
            affected_count=fast_rising_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            trend_direction=TrendDirection.IMPROVING if fast_rising_count > 0 else TrendDirection.STABLE,
            details={
                "fast_rising_queries": fast_rising_count,
                "total_queries_compared": total_queries,
                "avg_improvement": round(fast_rising["pos_change"].mean(), 2) if not fast_rising.empty else 0.0,
                "max_improvement": round(fast_rising["pos_change"].max(), 1) if not fast_rising.empty else 0.0,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 82 — Fast-Falling Query Count
    # ------------------------------------------------------------------ #
    def metric_fast_falling_query_count(self) -> MetricResult:
        """Queries that dropped > 5 spots in last 30d vs previous 30d."""
        df = self.get_df("query_page_date_90d")
        if df.empty:
            return self._error_result(82, "No query-page-date data available")

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])

        max_date = df["date"].max()
        current_start = max_date - timedelta(days=29)
        prev_start = max_date - timedelta(days=59)
        prev_end = max_date - timedelta(days=30)

        # Average position per query in each period
        current = (
            df[df["date"] >= current_start]
            .groupby("query")
            .agg(curr_pos=("position", "mean"), curr_imps=("impressions", "sum"))
            .reset_index()
        )
        previous = (
            df[(df["date"] >= prev_start) & (df["date"] <= prev_end)]
            .groupby("query")
            .agg(prev_pos=("position", "mean"), prev_imps=("impressions", "sum"))
            .reset_index()
        )

        merged = current.merge(previous, on="query", how="inner")
        if merged.empty:
            return self._error_result(82, "No queries found in both 30-day periods")

        # Position drop: negative change means position number increased (dropped)
        merged["pos_change"] = merged["prev_pos"] - merged["curr_pos"]
        merged["total_imps"] = merged["curr_imps"] + merged["prev_imps"]

        fast_falling = merged[merged["pos_change"] < -5.0].sort_values(
            "pos_change", ascending=True
        )
        fast_falling_count = len(fast_falling)
        total_queries = len(merged)
        falling_pct = (fast_falling_count / total_queries * 100) if total_queries > 0 else 0.0

        if falling_pct > 20:
            severity = Severity.HIGH
        elif falling_pct > 10:
            severity = Severity.MEDIUM
        elif falling_pct > 5:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        # Total impression impact of falling queries
        falling_impressions = fast_falling["total_imps"].sum() if not fast_falling.empty else 0

        summary = (
            f"{fast_falling_count:,} queries ({falling_pct:.1f}%) dropped more than "
            f"5 positions in the last 30 days compared to the previous 30 days "
            f"(out of {total_queries:,} total). These declining queries represent "
            f"{falling_impressions:,} impressions. "
            f"{'High proportion of fast-falling queries indicates significant ranking instability — immediate investigation needed.' if falling_pct > 20 else 'Query decline rate is within manageable range.'}"
        )

        # Show worst drops
        display_df = (
            fast_falling
            [["query", "prev_pos", "curr_pos", "pos_change", "total_imps"]]
            .head(25)
            .copy()
        )
        if not display_df.empty:
            display_df["prev_pos"] = display_df["prev_pos"].round(1)
            display_df["curr_pos"] = display_df["curr_pos"].round(1)
            display_df["pos_change"] = display_df["pos_change"].round(1)
            display_df.rename(columns={
                "prev_pos": "prev_30d_pos",
                "curr_pos": "last_30d_pos",
                "pos_change": "decline",
                "total_imps": "impressions",
            }, inplace=True)

        recommendations = []
        if falling_pct > 10:
            recommendations.extend([
                "Investigate the fastest-falling queries for content quality issues, competitor improvements, or algorithm impacts.",
                "Check if affected pages have technical issues (slow loading, broken links, mobile usability problems).",
                "Audit backlink profiles for pages ranking for these queries — lost links may explain ranking drops.",
                "Refresh and update content on affected pages to regain relevance and authority signals.",
                "Check for keyword cannibalization — multiple pages may be competing and causing position instability.",
            ])
        else:
            recommendations.extend([
                "Normal level of query decline. Continue monitoring for acceleration in the number of fast-falling queries.",
                "Proactively refresh content for queries showing early signs of decline before they drop further.",
            ])

        return self.create_result(
            metric_id=82,
            severity=severity,
            summary=summary,
            computed_value=round(falling_pct, 2),
            affected_count=fast_falling_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            trend_direction=TrendDirection.DECLINING if falling_pct > 10 else TrendDirection.STABLE,
            details={
                "fast_falling_queries": fast_falling_count,
                "total_queries_compared": total_queries,
                "falling_pct": round(falling_pct, 2),
                "falling_impressions": int(falling_impressions),
                "avg_decline": round(abs(fast_falling["pos_change"].mean()), 2) if not fast_falling.empty else 0.0,
                "max_decline": round(abs(fast_falling["pos_change"].min()), 1) if not fast_falling.empty else 0.0,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 83 — Rank Recovery Speed
    # ------------------------------------------------------------------ #
    def metric_rank_recovery_speed(self) -> MetricResult:
        """Find pages that dropped >50% in position over 365d, then check recovery.

        Recovery = returning to within 20% of original position.
        Reports recovery rate.
        """
        df = self.get_df("page_date_365d")
        if df.empty:
            return self._error_result(83, "No 365-day page-date data available")

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(["page", "date"])

        # Compute rolling average position per page per week to smooth data
        df["week"] = df["date"].dt.isocalendar().week.astype(int)
        df["year_week"] = df["date"].dt.strftime("%Y-%W")

        weekly = (
            df.groupby(["page", "year_week"])
            .agg(
                avg_position=("position", "mean"),
                total_impressions=("impressions", "sum"),
                week_start=("date", "min"),
            )
            .reset_index()
            .sort_values(["page", "week_start"])
        )

        # For each page, find baseline (first 4 weeks avg), worst point, and latest position
        recovery_data = []
        for page, group in weekly.groupby("page"):
            if len(group) < 8:
                continue

            group = group.sort_values("week_start")
            baseline_pos = group.head(4)["avg_position"].mean()
            current_pos = group.tail(4)["avg_position"].mean()

            # Find the worst (highest) position in the middle period
            worst_pos = group["avg_position"].max()
            worst_idx = group["avg_position"].idxmax()

            # Check if there was a significant drop (position increased by >50%)
            if baseline_pos <= 0:
                continue
            drop_pct = ((worst_pos - baseline_pos) / baseline_pos) * 100

            if drop_pct <= 50:
                continue

            # Check recovery: is current position within 20% of baseline?
            recovery_threshold = baseline_pos * 1.2
            recovered = current_pos <= recovery_threshold

            recovery_data.append({
                "page": page,
                "baseline_pos": round(baseline_pos, 1),
                "worst_pos": round(worst_pos, 1),
                "current_pos": round(current_pos, 1),
                "drop_pct": round(drop_pct, 1),
                "recovered": recovered,
                "total_impressions": group["total_impressions"].sum(),
            })

        if not recovery_data:
            return self.create_result(
                metric_id=83,
                severity=Severity.INSIGHT,
                summary=(
                    "No pages experienced a ranking drop of >50% during the 365-day "
                    "analysis period. This indicates strong ranking stability across all tracked pages."
                ),
                computed_value=100.0,
                affected_count=0,
                recommendations=[
                    "Continue maintaining content quality and link profiles to sustain ranking stability.",
                    "Set up monitoring alerts for any future significant position drops.",
                ],
                details={"pages_with_drops": 0, "recovery_rate": 100.0},
            )

        recovery_df = pd.DataFrame(recovery_data)
        total_dropped = len(recovery_df)
        recovered_count = recovery_df["recovered"].sum()
        not_recovered_count = total_dropped - recovered_count
        recovery_rate = (recovered_count / total_dropped * 100) if total_dropped > 0 else 0.0

        if recovery_rate < 40:
            severity = Severity.MEDIUM
        elif recovery_rate < 60:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{total_dropped:,} pages experienced a ranking drop of >50% during the "
            f"past year. Of these, {recovered_count:,} ({recovery_rate:.1f}%) recovered "
            f"to within 20% of their original position, while {not_recovered_count:,} "
            f"have not recovered. "
            f"{'Low recovery rate suggests systemic issues preventing ranking restoration.' if recovery_rate < 40 else 'Recovery rate indicates reasonable ranking resilience.'}"
        )

        display_df = (
            recovery_df
            .sort_values("drop_pct", ascending=False)
            [["page", "baseline_pos", "worst_pos", "current_pos", "drop_pct", "recovered"]]
            .head(25)
        )

        recommendations = []
        if recovery_rate < 60:
            recommendations.extend([
                "Audit non-recovered pages for content quality issues, broken links, or outdated information.",
                "Check if competitor content has surpassed your pages for the same queries — analyze what they do differently.",
                "Rebuild backlink profiles for non-recovered pages through targeted outreach and content promotion.",
                "Consider whether non-recovered pages need complete content overhauls rather than incremental updates.",
                "Evaluate if URL changes, redirects, or technical issues occurred during the drop period.",
            ])
        else:
            recommendations.extend([
                "Recovery rate is healthy. Document recovery patterns to build a playbook for future ranking drops.",
                "Focus on the remaining non-recovered pages with the highest baseline traffic potential.",
            ])

        return self.create_result(
            metric_id=83,
            severity=severity,
            summary=summary,
            computed_value=round(recovery_rate, 2),
            affected_count=not_recovered_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "pages_with_major_drops": total_dropped,
                "recovered_pages": int(recovered_count),
                "not_recovered_pages": int(not_recovered_count),
                "recovery_rate": round(recovery_rate, 2),
                "avg_drop_pct": round(recovery_df["drop_pct"].mean(), 1),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 84 — Position 11 Proximity Rate
    # ------------------------------------------------------------------ #
    def metric_position_11_proximity_rate(self) -> MetricResult:
        """Queries with avg position between 10.5 and 13.5 (almost page 1) as share of total."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(84, "No query data available")

        total_queries = len(df)
        if total_queries == 0:
            return self._error_result(84, "No queries in data")

        proximity = df[(df["position"] >= 10.5) & (df["position"] <= 13.5)]
        proximity_count = len(proximity)
        proximity_pct = (proximity_count / total_queries * 100)

        proximity_impressions = proximity["impressions"].sum()
        proximity_clicks = proximity["clicks"].sum()
        total_impressions = df["impressions"].sum()
        impression_share = (
            (proximity_impressions / total_impressions * 100)
            if total_impressions > 0 else 0.0
        )

        # Always MEDIUM — these are opportunities
        severity = Severity.MEDIUM

        summary = (
            f"{proximity_count:,} queries ({proximity_pct:.1f}%) have average positions "
            f"between 10.5 and 13.5, sitting just outside page 1. These 'almost page 1' "
            f"queries generate {proximity_impressions:,} impressions ({impression_share:.1f}% "
            f"of total) and {proximity_clicks:,} clicks. Moving these to page 1 could "
            f"dramatically increase click-through rates."
        )

        # Show top proximity queries by impressions
        display_df = (
            proximity
            .sort_values("impressions", ascending=False)
            [["query", "impressions", "clicks", "position", "ctr"]]
            .head(25)
            .copy()
        )
        if not display_df.empty:
            display_df["position"] = display_df["position"].round(1)

        recommendations = [
            "These are your highest-ROI optimization targets — a 1-3 position improvement puts them on page 1.",
            "Optimize title tags and headings for the top proximity queries to improve on-page relevance.",
            "Add 2-3 targeted internal links from high-authority pages to each URL ranking for these queries.",
            "Enhance content depth and comprehensiveness for proximity query topics to strengthen ranking signals.",
            "Build targeted backlinks to the pages ranking for the highest-impression proximity queries.",
        ]

        return self.create_result(
            metric_id=84,
            severity=severity,
            summary=summary,
            computed_value=round(proximity_pct, 2),
            affected_count=proximity_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            opportunity_value=f"{proximity_count:,} queries could reach page 1 with small improvements",
            details={
                "proximity_queries": proximity_count,
                "total_queries": total_queries,
                "proximity_pct": round(proximity_pct, 2),
                "proximity_impressions": int(proximity_impressions),
                "proximity_clicks": int(proximity_clicks),
                "proximity_impression_share": round(impression_share, 2),
            },
        )
