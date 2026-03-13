"""Click Behavior metrics (61-68).

Analyzes click patterns including zero-click rates at high positions,
single-click queries, click-to-impression acceleration, click concentration,
depth distribution, underperforming URLs, recovery rates, and
multi-device click patterns.
"""

import logging
from datetime import timedelta
from typing import Optional

import numpy as np
import pandas as pd

from metrics.base_metric import BaseMetricGroup
from models.metric_result import MetricResult, Severity, TrendDirection

logger = logging.getLogger(__name__)


class ClickBehaviorMetrics(BaseMetricGroup):
    """Metrics 61-68: Click Behavior analysis."""

    METRIC_REGISTRY: dict[int, str] = {
        61: "metric_high_position_zero_click_rate",
        62: "metric_single_click_query_rate",
        63: "metric_click_to_impression_acceleration_rate",
        64: "metric_top_query_click_concentration",
        65: "metric_click_depth_distribution",
        66: "metric_underperforming_high_impression_url_rate",
        67: "metric_click_recovery_rate",
        68: "metric_multi_device_click_share",
    }

    # ------------------------------------------------------------------ #
    # Metric 61 — High-Position Zero-Click Rate
    # ------------------------------------------------------------------ #
    def metric_high_position_zero_click_rate(self) -> MetricResult:
        """Queries with position <=5 and zero clicks as % of all position <=5 queries."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(61, "No query data available")

        high_pos = df[df["position"] <= 5.0]
        high_pos_count = len(high_pos)

        if high_pos_count == 0:
            return self.create_result(
                metric_id=61,
                severity=Severity.INSIGHT,
                summary="No queries rank in positions 1-5. Cannot compute zero-click rate for top positions.",
                computed_value=0.0,
                recommendations=[
                    "Focus on improving rankings to reach top-5 positions before analyzing click behavior.",
                ],
                details={"high_position_queries": 0},
            )

        zero_click_high = high_pos[high_pos["clicks"] == 0]
        zero_click_count = len(zero_click_high)
        zero_click_pct = (zero_click_count / high_pos_count * 100)

        # Total wasted impressions
        wasted_impressions = zero_click_high["impressions"].sum()
        total_high_impressions = high_pos["impressions"].sum()
        wasted_pct = (
            wasted_impressions / total_high_impressions * 100
        ) if total_high_impressions > 0 else 0.0

        # CRITICAL if >30%, HIGH if >20%
        if zero_click_pct > 30:
            severity = Severity.CRITICAL
        elif zero_click_pct > 20:
            severity = Severity.HIGH
        elif zero_click_pct > 10:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{zero_click_count:,} of {high_pos_count:,} queries in positions 1-5 "
            f"({zero_click_pct:.1f}%) have zero clicks, wasting {wasted_impressions:,} "
            f"impressions ({wasted_pct:.1f}% of top-position impressions). "
        )
        if zero_click_pct > 20:
            summary += (
                "This is a critical issue — top-ranking queries should generate clicks. "
                "Likely causes: SERP features answering the query directly, unappealing snippets, "
                "or branded queries captured by knowledge panels."
            )
        else:
            summary += "Zero-click rate in top positions is within normal range."

        # Show top zero-click high-position queries by impressions
        display_df = (
            zero_click_high
            .sort_values("impressions", ascending=False)
            [["query", "impressions", "position", "ctr"]]
            .head(25)
        ) if not zero_click_high.empty else None

        recommendations = []
        if zero_click_pct > 20:
            recommendations.extend([
                "Audit title tags and meta descriptions for zero-click top-ranking queries — they may lack click appeal.",
                "Check if Google featured snippets, knowledge panels, or PAA boxes are satisfying users without a click.",
                "Add compelling CTAs, numbers, or emotional triggers to meta descriptions to improve click-through.",
                "Consider targeting queries where a click is more likely (comparison, detailed guides) over informational queries answered directly in SERPs.",
                "Test different title tag formats (listicles, questions, numbers) for highest-impression zero-click queries.",
            ])
        elif zero_click_pct > 10:
            recommendations.extend([
                "Review zero-click queries for SERP feature impact. Some zero-click behavior is unavoidable for certain query types.",
                "Optimize snippets for high-impression zero-click queries to capture available click demand.",
            ])
        else:
            recommendations.append(
                "Top-position click-through is healthy. Continue monitoring for changes caused by SERP layout updates."
            )

        return self.create_result(
            metric_id=61,
            severity=severity,
            summary=summary,
            computed_value=round(zero_click_pct, 2),
            affected_count=zero_click_count,
            data_table=display_df,
            recommendations=recommendations,
            opportunity_value=(
                f"{wasted_impressions:,} top-position impressions not generating clicks"
                if zero_click_pct > 20 else None
            ),
            details={
                "zero_click_top_queries": zero_click_count,
                "total_top_queries": high_pos_count,
                "zero_click_rate_pct": round(zero_click_pct, 2),
                "wasted_impressions": int(wasted_impressions),
                "wasted_impression_pct": round(wasted_pct, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 62 — Single-Click Query Rate
    # ------------------------------------------------------------------ #
    def metric_single_click_query_rate(self) -> MetricResult:
        """Queries with exactly 1 click as % of all clicking queries."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(62, "No query data available")

        clicking_queries = df[df["clicks"] > 0]
        total_clicking = len(clicking_queries)

        if total_clicking == 0:
            return self.create_result(
                metric_id=62,
                severity=Severity.HIGH,
                summary="No queries generated clicks. Cannot compute single-click rate.",
                computed_value=0.0,
                recommendations=[
                    "Investigate why no queries are generating clicks. Check rankings, content quality, and SERP features.",
                ],
                details={"total_clicking_queries": 0},
            )

        single_click = clicking_queries[clicking_queries["clicks"] == 1]
        single_count = len(single_click)
        single_pct = (single_count / total_clicking * 100)

        # Performance of single-click vs multi-click queries
        multi_click = clicking_queries[clicking_queries["clicks"] > 1]
        single_avg_pos = single_click["position"].mean() if not single_click.empty else 0.0
        multi_avg_pos = multi_click["position"].mean() if not multi_click.empty else 0.0
        single_avg_ctr = single_click["ctr"].mean() if not single_click.empty else 0.0
        multi_avg_ctr = multi_click["ctr"].mean() if not multi_click.empty else 0.0
        single_impressions = single_click["impressions"].sum() if not single_click.empty else 0

        # MEDIUM if >60%
        if single_pct > 60:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{single_count:,} of {total_clicking:,} clicking queries ({single_pct:.1f}%) "
            f"have exactly 1 click. Single-click avg position: {single_avg_pos:.1f} vs "
            f"multi-click: {multi_avg_pos:.1f}. Single-click avg CTR: {single_avg_ctr * 100:.2f}% "
            f"vs multi-click: {multi_avg_ctr * 100:.2f}%."
        )

        if single_pct > 60:
            summary += (
                " High single-click rate indicates most clicking queries have very low "
                "click volumes — the site may lack queries that drive sustained traffic."
            )

        # Show single-click queries with highest impressions (opportunity)
        display_df = (
            single_click
            .sort_values("impressions", ascending=False)
            [["query", "clicks", "impressions", "position", "ctr"]]
            .head(25)
        ) if not single_click.empty else None

        recommendations = []
        if single_pct > 60:
            recommendations.extend([
                "Many queries generate only 1 click — focus on improving CTR for high-impression single-click queries.",
                "Optimize title tags and meta descriptions for queries with high impressions but only 1 click.",
                "Improve rankings for single-click queries with positions 5-15 to increase click volume.",
                "Identify single-click queries with high search volume potential for dedicated content investment.",
            ])
        else:
            recommendations.extend([
                "Healthy distribution of click volumes across queries.",
                "Continue monitoring single-click queries with high impressions for CTR improvement opportunities.",
            ])

        return self.create_result(
            metric_id=62,
            severity=severity,
            summary=summary,
            computed_value=round(single_pct, 2),
            affected_count=single_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "single_click_queries": single_count,
                "total_clicking_queries": total_clicking,
                "single_click_rate_pct": round(single_pct, 2),
                "single_click_avg_position": round(float(single_avg_pos), 2),
                "multi_click_avg_position": round(float(multi_avg_pos), 2),
                "single_click_impressions": int(single_impressions),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 63 — Click-to-Impression Acceleration Rate
    # ------------------------------------------------------------------ #
    def metric_click_to_impression_acceleration_rate(self) -> MetricResult:
        """% of URLs where click growth rate outpaces impression growth rate (30d vs prior 30d)."""
        df_90d = self.get_df("page_date_90d")
        df_30d = self.get_df("page_date_30d")

        if df_90d.empty:
            return self._error_result(63, "No 90-day page-date data available")

        df_90d = df_90d.copy()
        df_90d["date"] = pd.to_datetime(df_90d["date"])

        max_date = df_90d["date"].max()

        # Current period: last 30 days
        current_start = max_date - timedelta(days=29)
        # Previous period: 31-60 days ago
        prev_start = max_date - timedelta(days=59)
        prev_end = max_date - timedelta(days=30)

        current = df_90d[df_90d["date"] >= current_start]
        previous = df_90d[(df_90d["date"] >= prev_start) & (df_90d["date"] <= prev_end)]

        if current.empty or previous.empty:
            return self._error_result(63, "Insufficient data for 30-day period comparison")

        # Aggregate per page for each period
        curr_agg = (
            current.groupby("page")
            .agg(curr_clicks=("clicks", "sum"), curr_impressions=("impressions", "sum"))
            .reset_index()
        )
        prev_agg = (
            previous.groupby("page")
            .agg(prev_clicks=("clicks", "sum"), prev_impressions=("impressions", "sum"))
            .reset_index()
        )

        merged = pd.merge(curr_agg, prev_agg, on="page", how="inner")
        if merged.empty:
            return self._error_result(63, "No pages found in both periods for comparison")

        # Only consider pages with previous data > 0 to compute growth rates
        valid = merged[
            (merged["prev_clicks"] > 0) & (merged["prev_impressions"] > 0)
        ].copy()

        if valid.empty:
            return self.create_result(
                metric_id=63,
                severity=Severity.INSIGHT,
                summary="No pages had both clicks and impressions in the previous period for growth comparison.",
                computed_value=0.0,
                recommendations=[
                    "Ensure pages have sustained traffic over consecutive months for acceleration analysis.",
                ],
                details={"valid_pages": 0},
            )

        valid["click_growth"] = (
            (valid["curr_clicks"] - valid["prev_clicks"]) / valid["prev_clicks"]
        )
        valid["impression_growth"] = (
            (valid["curr_impressions"] - valid["prev_impressions"]) / valid["prev_impressions"]
        )

        # Accelerating = click growth > impression growth
        valid["is_accelerating"] = valid["click_growth"] > valid["impression_growth"]
        valid["acceleration_delta"] = (
            valid["click_growth"] - valid["impression_growth"]
        )

        total_valid = len(valid)
        accelerating = valid[valid["is_accelerating"]]
        accel_count = len(accelerating)
        accel_pct = (accel_count / total_valid * 100) if total_valid > 0 else 0.0

        decelerating = valid[~valid["is_accelerating"]]
        decel_count = len(decelerating)

        severity = Severity.INSIGHT

        # Determine trend
        if accel_pct >= 60:
            trend = TrendDirection.IMPROVING
        elif accel_pct <= 30:
            trend = TrendDirection.DECLINING
        else:
            trend = TrendDirection.STABLE

        # Show top accelerating pages
        if not accelerating.empty:
            top_accel = (
                accelerating
                .sort_values("acceleration_delta", ascending=False)
                .head(25)
                .copy()
            )
            top_accel["click_growth_pct"] = (top_accel["click_growth"] * 100).round(2)
            top_accel["impression_growth_pct"] = (top_accel["impression_growth"] * 100).round(2)
            top_accel["acceleration_delta_pct"] = (top_accel["acceleration_delta"] * 100).round(2)
            display_df = top_accel[[
                "page", "curr_clicks", "prev_clicks",
                "click_growth_pct", "impression_growth_pct", "acceleration_delta_pct",
            ]]
        else:
            display_df = None

        summary = (
            f"{accel_count:,} of {total_valid:,} pages ({accel_pct:.1f}%) show click "
            f"growth outpacing impression growth (accelerating). "
            f"{decel_count:,} pages ({100 - accel_pct:.1f}%) are decelerating "
            f"(impression growth exceeds click growth)."
        )

        recommendations = []
        if accel_pct >= 50:
            recommendations.extend([
                "Click acceleration is positive across most pages. CTR improvements or ranking gains are driving clicks faster than visibility growth.",
                "Investigate top accelerating pages to identify what is working (title tag changes, SERP feature wins, ranking improvements).",
                "Apply learnings from accelerating pages to decelerating ones.",
            ])
        elif accel_pct >= 30:
            recommendations.extend([
                "Mixed acceleration patterns. Review decelerating pages for CTR issues or ranking drops.",
                "Compare meta descriptions and title tags between accelerating and decelerating pages for optimization clues.",
            ])
        else:
            recommendations.extend([
                "Most pages are decelerating — impressions grow faster than clicks, indicating falling CTR.",
                "Audit title tags and meta descriptions site-wide for click appeal improvements.",
                "Check for SERP feature changes that may be absorbing clicks despite growing impressions.",
                "Review if position drops are causing fewer clicks despite maintained impressions.",
            ])

        return self.create_result(
            metric_id=63,
            severity=severity,
            summary=summary,
            computed_value=round(accel_pct, 2),
            affected_count=accel_count,
            data_table=display_df,
            recommendations=recommendations,
            trend_direction=trend,
            details={
                "accelerating_pages": accel_count,
                "decelerating_pages": decel_count,
                "total_valid_pages": total_valid,
                "acceleration_rate_pct": round(accel_pct, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 64 — Top Query Click Concentration
    # ------------------------------------------------------------------ #
    def metric_top_query_click_concentration(self) -> MetricResult:
        """Per page, what % of clicks come from the top query. Report avg across pages."""
        df = self.get_df("query_page_90d")
        if df.empty:
            return self._error_result(64, "No query-page data available")

        # Only consider pages with clicks
        page_clicks = df.groupby("page")["clicks"].sum().reset_index()
        pages_with_clicks = page_clicks[page_clicks["clicks"] > 0]["page"]
        df_clicking = df[df["page"].isin(pages_with_clicks)].copy()

        if df_clicking.empty:
            return self.create_result(
                metric_id=64,
                severity=Severity.HIGH,
                summary="No pages have clicking queries. Cannot compute click concentration.",
                computed_value=0.0,
                recommendations=[
                    "Investigate why pages are not generating clicks from queries.",
                ],
                details={"pages_with_clicks": 0},
            )

        # For each page, find the top query's click share
        page_total_clicks = df_clicking.groupby("page")["clicks"].sum()
        page_top_query_clicks = df_clicking.groupby("page")["clicks"].max()

        concentration = (page_top_query_clicks / page_total_clicks * 100).reset_index()
        concentration.columns = ["page", "top_query_click_share_pct"]
        concentration = concentration.sort_values("top_query_click_share_pct", ascending=False)

        avg_concentration = concentration["top_query_click_share_pct"].mean()
        total_pages = len(concentration)

        # Pages with very high concentration (>70%)
        high_conc = concentration[concentration["top_query_click_share_pct"] > 70]
        high_conc_count = len(high_conc)
        high_conc_pct = (high_conc_count / total_pages * 100) if total_pages > 0 else 0.0

        # HIGH if avg >70% (single-query dependency)
        if avg_concentration > 70:
            severity = Severity.HIGH
        elif avg_concentration > 50:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        # Enrich display with top query name and page total clicks
        display_rows = []
        for _, row in concentration.head(25).iterrows():
            page = row["page"]
            page_data = df_clicking[df_clicking["page"] == page]
            total_page_clicks = page_data["clicks"].sum()
            top_query_row = page_data.loc[page_data["clicks"].idxmax()]
            display_rows.append({
                "page": page,
                "top_query": top_query_row["query"],
                "top_query_clicks": int(top_query_row["clicks"]),
                "total_page_clicks": int(total_page_clicks),
                "top_query_share_pct": round(row["top_query_click_share_pct"], 2),
            })
        display_df = pd.DataFrame(display_rows) if display_rows else None

        summary = (
            f"Average top-query click concentration is {avg_concentration:.1f}% across "
            f"{total_pages:,} pages. {high_conc_count:,} pages ({high_conc_pct:.1f}%) "
            f"have >70% of their clicks coming from a single query."
        )

        if avg_concentration > 70:
            summary += (
                " High concentration creates fragility — if a page loses its top query ranking, "
                "most of its click traffic disappears."
            )

        recommendations = []
        if avg_concentration > 70:
            recommendations.extend([
                "Pages are heavily dependent on single queries. Expand content to rank for a broader set of related queries.",
                "Add supporting subtopics, FAQs, and related content to high-concentration pages to attract more query diversity.",
                "Build internal links from diverse topic pages to reduce single-query dependency.",
                "Monitor top-query rankings closely on high-concentration pages — any ranking drop will cause significant traffic loss.",
            ])
        elif avg_concentration > 50:
            recommendations.extend([
                "Moderate click concentration. Identify pages with >70% concentration for targeted content expansion.",
                "Diversify title tags and headings to target a broader range of related queries per page.",
            ])
        else:
            recommendations.append(
                "Click distribution across queries is healthy. Pages attract traffic from diverse query sets."
            )

        return self.create_result(
            metric_id=64,
            severity=severity,
            summary=summary,
            computed_value=round(avg_concentration, 2),
            affected_count=high_conc_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "avg_top_query_concentration_pct": round(avg_concentration, 2),
                "pages_above_70pct": high_conc_count,
                "total_pages_with_clicks": total_pages,
                "high_concentration_pct": round(high_conc_pct, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 65 — Click Depth Distribution
    # ------------------------------------------------------------------ #
    def metric_click_depth_distribution(self) -> MetricResult:
        """Total clicks distributed across position buckets (1-3, 4-10, 11-20, 21-50, 51+)."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(65, "No query data available")

        total_clicks = df["clicks"].sum()
        if total_clicks == 0:
            return self.create_result(
                metric_id=65,
                severity=Severity.HIGH,
                summary="No clicks recorded. Cannot compute click depth distribution.",
                computed_value=0.0,
                recommendations=[
                    "Investigate why the site is not generating clicks from any position bucket.",
                ],
                details={"total_clicks": 0},
            )

        # Define position buckets
        buckets = [
            ("1-3", 0.0, 3.0),
            ("4-10", 3.0, 10.0),
            ("11-20", 10.0, 20.0),
            ("21-50", 20.0, 50.0),
            ("51+", 50.0, float("inf")),
        ]

        rows = []
        for label, low, high in buckets:
            if label == "1-3":
                bucket_df = df[df["position"] <= high]
            elif label == "51+":
                bucket_df = df[df["position"] > low]
            else:
                bucket_df = df[(df["position"] > low) & (df["position"] <= high)]

            bucket_clicks = bucket_df["clicks"].sum()
            bucket_impressions = bucket_df["impressions"].sum()
            bucket_queries = len(bucket_df)
            bucket_share = (bucket_clicks / total_clicks * 100) if total_clicks > 0 else 0.0
            avg_ctr = bucket_df["ctr"].mean() if not bucket_df.empty else 0.0

            rows.append({
                "position_bucket": label,
                "clicks": int(bucket_clicks),
                "impressions": int(bucket_impressions),
                "queries": bucket_queries,
                "click_share_pct": round(bucket_share, 2),
                "avg_ctr_pct": round(float(avg_ctr) * 100, 2),
            })

        display_df = pd.DataFrame(rows)

        # Key metrics for severity
        top_3_share = rows[0]["click_share_pct"]
        page_1_share = rows[0]["click_share_pct"] + rows[1]["click_share_pct"]
        deep_clicks = rows[3]["clicks"] + rows[4]["clicks"]  # pos 21+
        deep_share = rows[3]["click_share_pct"] + rows[4]["click_share_pct"]

        severity = Severity.INSIGHT

        summary = (
            f"Click distribution across position buckets: "
            f"Positions 1-3 capture {top_3_share:.1f}%, "
            f"page 1 (1-10) captures {page_1_share:.1f}%, "
            f"and positions 21+ capture {deep_share:.1f}% of {total_clicks:,} total clicks. "
        )
        if page_1_share < 60:
            summary += (
                "Significant clicks come from beyond page 1, which is unusual and may indicate "
                "niche queries or topics with less competitive SERPs."
            )
        else:
            summary += "Click distribution follows expected patterns with most clicks from top positions."

        recommendations = []
        if page_1_share < 60:
            recommendations.extend([
                "Unusual amount of clicks from page 2+ positions. Investigate which queries drive these deep clicks.",
                "Prioritize moving page 2+ queries to page 1 — even small ranking gains can significantly increase clicks.",
                "Review content quality for pages ranking beyond position 10 that still generate clicks.",
            ])
        elif top_3_share < 40:
            recommendations.extend([
                "Clicks are spread across page 1 positions. Focus on pushing position 4-10 queries into top 3 for maximum impact.",
                "Optimize title tags and meta descriptions for position 4-10 queries to improve CTR.",
            ])
        else:
            recommendations.append(
                "Click distribution is healthy with strong top-position performance. Continue maintaining and improving top rankings."
            )

        return self.create_result(
            metric_id=65,
            severity=severity,
            summary=summary,
            computed_value=round(page_1_share, 2),
            affected_count=int(total_clicks),
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_clicks": int(total_clicks),
                "top_3_click_share_pct": round(top_3_share, 2),
                "page_1_click_share_pct": round(page_1_share, 2),
                "deep_click_share_pct": round(deep_share, 2),
                "distribution": rows,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 66 — Underperforming High-Impression URL Rate
    # ------------------------------------------------------------------ #
    def metric_underperforming_high_impression_url_rate(self) -> MetricResult:
        """URLs with impressions in top 25% but CTR in bottom 25%."""
        df = self.get_df("page_90d")
        if df.empty:
            return self._error_result(66, "No page data available")

        if len(df) < 4:
            return self.create_result(
                metric_id=66,
                severity=Severity.INSIGHT,
                summary=f"Only {len(df)} URLs found. Need at least 4 for quartile analysis.",
                computed_value=0.0,
                recommendations=[
                    "Ensure sufficient page data is available for underperformance analysis.",
                ],
                details={"total_pages": len(df)},
            )

        total_urls = len(df)

        # Calculate quartile thresholds
        imp_75th = df["impressions"].quantile(0.75)
        ctr_25th = df["ctr"].quantile(0.25)

        # High impressions AND low CTR
        underperforming = df[
            (df["impressions"] >= imp_75th) & (df["ctr"] <= ctr_25th)
        ].copy()
        under_count = len(underperforming)
        under_pct = (under_count / total_urls * 100) if total_urls > 0 else 0.0

        # Calculate wasted opportunity
        underperforming_impressions = underperforming["impressions"].sum() if not underperforming.empty else 0
        underperforming_clicks = underperforming["clicks"].sum() if not underperforming.empty else 0
        site_avg_ctr = df["ctr"].mean()
        potential_clicks = int(underperforming_impressions * site_avg_ctr) if site_avg_ctr > 0 else 0
        click_gap = potential_clicks - int(underperforming_clicks)

        # HIGH if >20%
        if under_pct > 20:
            severity = Severity.HIGH
        elif under_pct > 10:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        # Show underperforming URLs sorted by impressions
        if not underperforming.empty:
            display_df = (
                underperforming
                .sort_values("impressions", ascending=False)
                [["page", "impressions", "clicks", "ctr", "position"]]
                .head(25)
                .copy()
            )
            display_df["ctr_pct"] = (display_df["ctr"] * 100).round(2)
        else:
            display_df = None

        summary = (
            f"{under_count:,} of {total_urls:,} URLs ({under_pct:.1f}%) have high "
            f"impressions (>={imp_75th:.0f}) but low CTR (<={ctr_25th * 100:.2f}%). "
            f"These pages have {underperforming_impressions:,} impressions but only "
            f"{int(underperforming_clicks):,} clicks. "
            f"At site-average CTR, they could generate ~{potential_clicks:,} clicks "
            f"(gap of ~{click_gap:,} clicks)."
        )

        recommendations = []
        if under_pct > 10:
            recommendations.extend([
                "Rewrite title tags and meta descriptions for underperforming high-impression URLs to improve click appeal.",
                "Analyze the SERP landscape for these URLs — SERP features may be suppressing organic click-through.",
                "Check if position degradation is causing low CTR despite high impressions (pages may be losing rankings).",
                "Consider adding structured data (review stars, FAQ, breadcrumbs) to make listings more visually compelling.",
                "Test different title formats — numbers, questions, and power words can significantly improve CTR.",
            ])
        else:
            recommendations.extend([
                "Few URLs show the high-impression / low-CTR pattern. Continue monitoring for emerging underperformers.",
                "Regularly audit CTR performance for your most visible pages.",
            ])

        return self.create_result(
            metric_id=66,
            severity=severity,
            summary=summary,
            computed_value=round(under_pct, 2),
            affected_count=under_count,
            data_table=display_df,
            recommendations=recommendations,
            opportunity_value=(
                f"~{click_gap:,} additional clicks possible at site-average CTR"
                if click_gap > 0 else None
            ),
            details={
                "underperforming_urls": under_count,
                "total_urls": total_urls,
                "underperforming_pct": round(under_pct, 2),
                "impression_threshold": float(imp_75th),
                "ctr_threshold": round(float(ctr_25th), 4),
                "wasted_impressions": int(underperforming_impressions),
                "current_clicks": int(underperforming_clicks),
                "potential_clicks_at_avg_ctr": potential_clicks,
                "click_gap": click_gap,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 67 — Click Recovery Rate (Post-Drop)
    # ------------------------------------------------------------------ #
    def metric_click_recovery_rate(self) -> MetricResult:
        """URLs that had >50% click drop in any 30d period and recovered within 90 days."""
        df = self.get_df("page_date_365d")
        if df.empty:
            return self._error_result(67, "No 365-day page-date data available")

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])

        # Aggregate clicks per page per month
        df["month"] = df["date"].dt.to_period("M")
        monthly = (
            df.groupby(["page", "month"])["clicks"]
            .sum()
            .reset_index()
            .sort_values(["page", "month"])
        )

        # Convert period to ordinal for comparison
        monthly["month_ord"] = monthly["month"].apply(lambda x: x.ordinal)

        pages = monthly["page"].unique()
        drop_pages = []
        recovered_pages = []

        for page in pages:
            page_data = monthly[monthly["page"] == page].sort_values("month_ord")
            if len(page_data) < 3:
                continue

            clicks_list = page_data["clicks"].values
            months_list = page_data["month_ord"].values

            for i in range(1, len(clicks_list)):
                prev_clicks = clicks_list[i - 1]
                curr_clicks = clicks_list[i]

                if prev_clicks == 0:
                    continue

                drop_pct = (prev_clicks - curr_clicks) / prev_clicks

                if drop_pct > 0.5:
                    # >50% drop detected
                    drop_month_ord = months_list[i]
                    pre_drop_clicks = prev_clicks

                    # Check recovery within next 3 months
                    recovery_window = page_data[
                        (page_data["month_ord"] > drop_month_ord)
                        & (page_data["month_ord"] <= drop_month_ord + 3)
                    ]

                    recovered = False
                    if not recovery_window.empty:
                        # Recovery = reaching at least 80% of pre-drop clicks
                        max_recovery = recovery_window["clicks"].max()
                        if max_recovery >= pre_drop_clicks * 0.8:
                            recovered = True

                    drop_pages.append({
                        "page": page,
                        "pre_drop_clicks": int(prev_clicks),
                        "drop_clicks": int(curr_clicks),
                        "drop_pct": round(drop_pct * 100, 1),
                        "recovered": recovered,
                        "recovery_max": int(recovery_window["clicks"].max()) if not recovery_window.empty else 0,
                    })

                    if recovered:
                        recovered_pages.append(page)
                    # Only track the first significant drop per page
                    break

        total_drops = len(drop_pages)
        total_recovered = len(set(recovered_pages))

        if total_drops == 0:
            return self.create_result(
                metric_id=67,
                severity=Severity.INSIGHT,
                summary=(
                    "No URLs experienced a >50% click drop in any 30-day period during the "
                    "past year. Click traffic has been stable."
                ),
                computed_value=100.0,
                recommendations=[
                    "No significant click drops detected. Continue monitoring for sudden traffic changes.",
                ],
                details={
                    "total_drops": 0,
                    "total_recovered": 0,
                    "total_pages_analyzed": len(pages),
                },
            )

        recovery_rate = (total_recovered / total_drops * 100) if total_drops > 0 else 0.0

        if recovery_rate < 30:
            severity = Severity.HIGH
        elif recovery_rate < 50:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        # Build display table
        drop_df = pd.DataFrame(drop_pages).sort_values("pre_drop_clicks", ascending=False)
        display_df = drop_df.head(25)

        not_recovered = total_drops - total_recovered

        summary = (
            f"{total_drops:,} URLs experienced a >50% click drop in some month. "
            f"{total_recovered:,} ({recovery_rate:.1f}%) recovered within 90 days, "
            f"while {not_recovered:,} did not recover."
        )

        if recovery_rate < 50:
            summary += (
                " Low recovery rate suggests systemic issues — ranking losses, algorithm impacts, "
                "or content decay may be preventing traffic rebound."
            )

        recommendations = []
        if recovery_rate < 50:
            recommendations.extend([
                "Audit non-recovered URLs for content staleness, ranking drops, or technical issues.",
                "Check if algorithm updates coincided with click drops — content may need realignment with updated ranking signals.",
                "Refresh and expand content on drop pages to regain lost rankings and traffic.",
                "Build new internal links and backlinks to non-recovered pages to restore authority signals.",
                "Investigate if competitors published superior content that displaced your rankings.",
            ])
        else:
            recommendations.extend([
                "Reasonable recovery rate. Continue monitoring for new click drops and implementing rapid response protocols.",
                "Document what recovery actions were taken on successfully recovered pages to create a playbook.",
            ])

        return self.create_result(
            metric_id=67,
            severity=severity,
            summary=summary,
            computed_value=round(recovery_rate, 2),
            affected_count=total_drops,
            data_table=display_df,
            recommendations=recommendations,
            trend_direction=(
                TrendDirection.IMPROVING if recovery_rate >= 60
                else TrendDirection.DECLINING if recovery_rate < 40
                else TrendDirection.STABLE
            ),
            details={
                "total_drop_pages": total_drops,
                "recovered_pages": total_recovered,
                "not_recovered_pages": not_recovered,
                "recovery_rate_pct": round(recovery_rate, 2),
                "total_pages_analyzed": len(pages),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 68 — Multi-Device Click Share
    # ------------------------------------------------------------------ #
    def metric_multi_device_click_share(self) -> MetricResult:
        """Percentage of pages receiving clicks from 2+ device types."""
        df = self.get_df("page_device_90d")
        if df.empty:
            return self._error_result(68, "No page-device data available")

        # Only consider rows with clicks
        clicking = df[df["clicks"] > 0].copy()

        if clicking.empty:
            return self.create_result(
                metric_id=68,
                severity=Severity.INSIGHT,
                summary="No pages have device-level click data. Cannot compute multi-device share.",
                computed_value=0.0,
                recommendations=[
                    "Ensure page-device data is available for cross-device click analysis.",
                ],
                details={"clicking_pages": 0},
            )

        # Count distinct devices with clicks per page
        device_counts = (
            clicking.groupby("page")["device"]
            .nunique()
            .reset_index()
            .rename(columns={"device": "device_count"})
        )

        total_pages = len(device_counts)
        multi_device = device_counts[device_counts["device_count"] >= 2]
        multi_count = len(multi_device)
        multi_pct = (multi_count / total_pages * 100) if total_pages > 0 else 0.0

        single_device = device_counts[device_counts["device_count"] == 1]
        single_count = len(single_device)

        # Available device types
        available_devices = sorted(clicking["device"].unique().tolist())

        # Enrich with click details per device for top multi-device pages
        if not multi_device.empty:
            top_multi = multi_device.sort_values("device_count", ascending=False).head(25)
            display_rows = []
            for _, row in top_multi.iterrows():
                page = row["page"]
                page_data = clicking[clicking["page"] == page]
                device_clicks = page_data.groupby("device")["clicks"].sum().to_dict()
                total_page_clicks = page_data["clicks"].sum()
                display_rows.append({
                    "page": page,
                    "device_count": int(row["device_count"]),
                    "total_clicks": int(total_page_clicks),
                    **{f"{d}_clicks": int(device_clicks.get(d, 0)) for d in available_devices},
                })
            display_df = pd.DataFrame(display_rows)
        else:
            display_df = None

        # Overall device click distribution
        device_totals = clicking.groupby("device")["clicks"].sum().to_dict()

        severity = Severity.INSIGHT

        summary = (
            f"{multi_count:,} of {total_pages:,} pages ({multi_pct:.1f}%) receive clicks "
            f"from 2 or more device types. {single_count:,} pages receive clicks from "
            f"only one device type. "
            f"Available devices: {', '.join(available_devices)}. "
        )

        if multi_pct < 30:
            summary += (
                "Low multi-device coverage may indicate mobile or desktop-specific "
                "content gaps, or that many pages have very low overall click volumes."
            )
        else:
            summary += "Healthy cross-device click distribution indicates broad content accessibility."

        recommendations = []
        if multi_pct < 30:
            recommendations.extend([
                "Low multi-device click share may indicate mobile optimization issues or desktop-only content.",
                "Check if single-device pages have mobile usability issues preventing mobile clicks.",
                "Review responsive design and Core Web Vitals for pages that only receive desktop clicks.",
                "Ensure content formatting works well across devices — tables, images, and interactive elements may not render properly on mobile.",
            ])
        elif multi_pct < 60:
            recommendations.extend([
                "Moderate multi-device coverage. Identify single-device pages and check for device-specific issues.",
                "Test page load speed and usability across devices for your most important content.",
            ])
        else:
            recommendations.append(
                "Strong multi-device click coverage. Content is accessible and performing across device types."
            )

        return self.create_result(
            metric_id=68,
            severity=severity,
            summary=summary,
            computed_value=round(multi_pct, 2),
            affected_count=multi_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "multi_device_pages": multi_count,
                "single_device_pages": single_count,
                "total_pages_with_clicks": total_pages,
                "multi_device_pct": round(multi_pct, 2),
                "available_devices": available_devices,
                "device_click_totals": {k: int(v) for k, v in device_totals.items()},
            },
        )
