"""Content Health & Decay metrics (45-48).

Analyzes content freshness, thin content, efficiency, and
new URL traction patterns across the site.
"""

import logging
from datetime import timedelta

import pandas as pd

from metrics.base_metric import BaseMetricGroup
from models.metric_result import MetricResult, Severity, TrendDirection

logger = logging.getLogger(__name__)


class ContentHealthMetrics(BaseMetricGroup):
    """Metrics 45-48: Content Health & Decay analysis."""

    METRIC_REGISTRY: dict[int, str] = {
        45: "metric_content_decay_index",
        46: "metric_thin_content_query_rate",
        47: "metric_content_efficiency_ratio",
        48: "metric_mom_new_url_click_share",
    }

    # ------------------------------------------------------------------ #
    # Metric 45 — Content Decay Index
    # ------------------------------------------------------------------ #
    def metric_content_decay_index(self) -> MetricResult:
        """Compare per-page clicks in most recent 30d vs same 30d one year ago."""
        df_90d = self.get_df("page_date_90d")
        df_365d = self.get_df("page_date_365d")

        if df_365d.empty:
            return self._error_result(45, "No 365-day page-date data available")
        if df_90d.empty:
            return self._error_result(45, "No 90-day page-date data available")

        df_365d = df_365d.copy()
        df_365d["date"] = pd.to_datetime(df_365d["date"])
        df_90d = df_90d.copy()
        df_90d["date"] = pd.to_datetime(df_90d["date"])

        # Recent 30d window: last 30 days from the 90d dataset
        max_date_recent = df_90d["date"].max()
        recent_start = max_date_recent - timedelta(days=29)
        recent_df = df_90d[df_90d["date"] >= recent_start]

        # Year-ago 30d window: same calendar period one year back from the 365d dataset
        yago_end = recent_start - timedelta(days=335)  # ~365 - 30
        yago_start = yago_end - timedelta(days=29)

        yago_df = df_365d[
            (df_365d["date"] >= yago_start) & (df_365d["date"] <= yago_end)
        ]

        if yago_df.empty:
            # Fallback: use the oldest 30 days available in the 365d dataset
            min_date = df_365d["date"].min()
            yago_start = min_date
            yago_end = min_date + timedelta(days=29)
            yago_df = df_365d[
                (df_365d["date"] >= yago_start) & (df_365d["date"] <= yago_end)
            ]

        if yago_df.empty:
            return self._error_result(
                45, "Insufficient historical data for year-over-year comparison"
            )

        # Aggregate clicks per page in each window
        recent_clicks = (
            recent_df.groupby("page")["clicks"]
            .sum()
            .reset_index()
            .rename(columns={"clicks": "recent_clicks"})
        )
        yago_clicks = (
            yago_df.groupby("page")["clicks"]
            .sum()
            .reset_index()
            .rename(columns={"clicks": "yago_clicks"})
        )

        merged = recent_clicks.merge(yago_clicks, on="page", how="inner")

        if merged.empty:
            return self._error_result(
                45, "No overlapping URLs between current and year-ago periods"
            )

        # Only consider pages that had meaningful traffic in the old period
        merged = merged[merged["yago_clicks"] >= 1].copy()

        if merged.empty:
            return self.create_result(
                metric_id=45,
                severity=Severity.INSIGHT,
                summary="No pages had clicks in the year-ago period to compare against.",
                computed_value=0.0,
                affected_count=0,
                recommendations=[
                    "This site may be too new for year-over-year decay analysis. "
                    "Re-run this audit once 12+ months of data are available."
                ],
            )

        merged["decay_rate"] = (
            (merged["yago_clicks"] - merged["recent_clicks"]) / merged["yago_clicks"]
        )

        decaying = merged[merged["decay_rate"] > 0.5]
        decay_count = len(decaying)
        total_compared = len(merged)
        decay_pct = (decay_count / total_compared * 100) if total_compared > 0 else 0.0

        # Average decay rate across all compared URLs
        avg_decay = merged["decay_rate"].mean() * 100

        if decay_pct > 40:
            severity = Severity.CRITICAL
        elif decay_pct > 25:
            severity = Severity.HIGH
        elif decay_pct > 10:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        trend = TrendDirection.DECLINING if decay_pct > 10 else TrendDirection.STABLE

        # Build data table — show the most decayed pages
        display_df = (
            decaying.sort_values("decay_rate", ascending=False)
            .head(25)
            .copy()
        )
        display_df["decay_rate_pct"] = (display_df["decay_rate"] * 100).round(1)
        display_df = display_df[
            ["page", "recent_clicks", "yago_clicks", "decay_rate_pct"]
        ]

        summary = (
            f"{decay_count:,} of {total_compared:,} comparable URLs ({decay_pct:.1f}%) "
            f"show >50% click decay year-over-year. "
            f"Average decay rate across all compared URLs is {avg_decay:.1f}%. "
            f"Significant content decay can indicate outdated content, lost rankings, "
            f"or shifting search intent."
        )

        recommendations = []
        if decay_pct > 10:
            recommendations.extend([
                "Audit the most decayed URLs for content freshness — update statistics, examples, and references.",
                "Check if decaying pages lost key rankings by reviewing position changes for their top queries.",
                "Evaluate whether search intent has shifted for the queries these pages used to rank for.",
                "Consider consolidating low-performing decayed pages into stronger, more comprehensive resources.",
                "Add new internal links from high-authority pages to boost decaying content.",
            ])
        else:
            recommendations.append(
                "Content decay is minimal. Continue monitoring and proactively refreshing "
                "older content before decay becomes significant."
            )

        return self.create_result(
            metric_id=45,
            severity=severity,
            summary=summary,
            computed_value=round(decay_pct, 2),
            affected_count=decay_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            trend_direction=trend,
            details={
                "total_compared_urls": total_compared,
                "decaying_urls": decay_count,
                "decay_pct": round(decay_pct, 2),
                "avg_decay_rate_pct": round(avg_decay, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 46 — Thin Content Query Rate
    # ------------------------------------------------------------------ #
    def metric_thin_content_query_rate(self) -> MetricResult:
        """Pages with fewer than 3 unique queries are considered thin content."""
        df = self.get_df("query_page_90d")
        if df.empty:
            return self._error_result(46, "No query-page data available")

        page_query_counts = (
            df.groupby("page")["query"]
            .nunique()
            .reset_index()
            .rename(columns={"query": "unique_queries"})
        )

        total_pages = len(page_query_counts)
        if total_pages == 0:
            return self._error_result(46, "No pages found in query-page data")

        thin_pages = page_query_counts[page_query_counts["unique_queries"] < 3]
        thin_count = len(thin_pages)
        thin_pct = (thin_count / total_pages * 100)

        # Also gather click data for thin pages to assess impact
        page_clicks = (
            df.groupby("page")["clicks"]
            .sum()
            .reset_index()
            .rename(columns={"clicks": "total_clicks"})
        )
        thin_detail = thin_pages.merge(page_clicks, on="page", how="left").fillna(0)
        thin_detail = thin_detail.sort_values("total_clicks", ascending=False)

        total_clicks = df["clicks"].sum()
        thin_clicks = thin_detail["total_clicks"].sum()
        thin_click_share = (thin_clicks / total_clicks * 100) if total_clicks > 0 else 0.0

        if thin_pct > 50:
            severity = Severity.CRITICAL
        elif thin_pct > 35:
            severity = Severity.HIGH
        elif thin_pct > 20:
            severity = Severity.MEDIUM
        elif thin_pct > 10:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{thin_count:,} of {total_pages:,} pages ({thin_pct:.1f}%) have fewer "
            f"than 3 unique queries, indicating thin content with limited search visibility. "
            f"These thin pages account for {thin_click_share:.1f}% of total clicks. "
            f"Pages attracting very few queries may lack topical depth or relevance."
        )

        display_df = thin_detail[["page", "unique_queries", "total_clicks"]].head(25)

        recommendations = []
        if thin_pct > 20:
            recommendations.extend([
                "Review thin pages to determine if they serve a purpose — consider expanding, consolidating, or removing them.",
                "Add structured content (FAQs, how-tos, related subtopics) to thin pages to attract more query variety.",
                "Merge overlapping thin pages that target similar topics into a single comprehensive resource.",
                "Check if thin pages have technical issues (noindex, canonical problems) that limit query visibility.",
                "Evaluate whether thin pages are orphaned — ensure they have proper internal linking.",
            ])
        else:
            recommendations.append(
                "Thin content rate is within a healthy range. Periodically review "
                "pages with very few queries for consolidation opportunities."
            )

        return self.create_result(
            metric_id=46,
            severity=severity,
            summary=summary,
            computed_value=round(thin_pct, 2),
            affected_count=thin_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "total_pages": total_pages,
                "thin_pages": thin_count,
                "thin_pct": round(thin_pct, 2),
                "thin_click_share_pct": round(thin_click_share, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 47 — Content Efficiency Ratio
    # ------------------------------------------------------------------ #
    def metric_content_efficiency_ratio(self) -> MetricResult:
        """Clicks per unique query for each page — higher means more efficient."""
        df = self.get_df("query_page_90d")
        if df.empty:
            return self._error_result(47, "No query-page data available")

        page_stats = df.groupby("page").agg(
            total_clicks=("clicks", "sum"),
            unique_queries=("query", "nunique"),
        ).reset_index()

        if page_stats.empty or page_stats["unique_queries"].sum() == 0:
            return self._error_result(47, "No query data to compute efficiency ratio")

        page_stats["efficiency_ratio"] = (
            page_stats["total_clicks"] / page_stats["unique_queries"]
        ).round(4)

        # Site-wide average
        total_clicks = page_stats["total_clicks"].sum()
        total_unique_queries = page_stats["unique_queries"].sum()
        site_avg_ratio = (
            total_clicks / total_unique_queries if total_unique_queries > 0 else 0.0
        )

        # Flag pages with ratio < 0.1 (fewer than 1 click per 10 queries)
        inefficient = page_stats[page_stats["efficiency_ratio"] < 0.1]
        inefficient_count = len(inefficient)
        total_pages = len(page_stats)
        inefficient_pct = (
            (inefficient_count / total_pages * 100) if total_pages > 0 else 0.0
        )

        # Median ratio for context
        median_ratio = page_stats["efficiency_ratio"].median()

        if site_avg_ratio < 0.1:
            severity = Severity.HIGH
        elif site_avg_ratio < 0.3:
            severity = Severity.MEDIUM
        elif site_avg_ratio < 0.5:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"Site-wide content efficiency ratio (clicks/unique queries) is {site_avg_ratio:.3f}. "
            f"Median per-page ratio is {median_ratio:.3f}. "
            f"{inefficient_count:,} of {total_pages:,} pages ({inefficient_pct:.1f}%) have a ratio "
            f"below 0.1, meaning they attract queries but fail to convert impressions into clicks."
        )

        # Display: show least efficient pages with enough queries to matter
        display_candidates = page_stats[page_stats["unique_queries"] >= 2].copy()
        display_df = (
            display_candidates
            .sort_values("efficiency_ratio", ascending=True)
            [["page", "total_clicks", "unique_queries", "efficiency_ratio"]]
            .head(25)
        )

        recommendations = []
        if site_avg_ratio < 0.3:
            recommendations.extend([
                "Optimize title tags and meta descriptions for low-efficiency pages to improve click-through rates.",
                "Verify that low-efficiency pages match user search intent — content may need restructuring.",
                "Check ranking positions for low-efficiency pages — low positions naturally reduce click probability.",
                "Add structured data to improve SERP presentation and entice clicks.",
                "Consider whether some low-efficiency pages should be redirected to higher-performing alternatives.",
            ])
        else:
            recommendations.append(
                "Content efficiency is healthy overall. Focus on the bottom-performing pages "
                "to bring them closer to the site average."
            )

        return self.create_result(
            metric_id=47,
            severity=severity,
            summary=summary,
            computed_value=round(site_avg_ratio, 4),
            affected_count=inefficient_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "site_avg_efficiency": round(site_avg_ratio, 4),
                "median_efficiency": round(float(median_ratio), 4),
                "inefficient_pages": inefficient_count,
                "total_pages": total_pages,
                "inefficient_pct": round(inefficient_pct, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 48 — MoM New URL Click Share
    # ------------------------------------------------------------------ #
    def metric_mom_new_url_click_share(self) -> MetricResult:
        """Click share of URLs appearing in current 30d that were absent in previous 30-60d."""
        df_90d = self.get_df("page_date_90d")
        df_30d = self.get_df("page_date_30d")

        # Prefer 90d data for deriving both periods; fall back to 30d for current
        if df_90d.empty and df_30d.empty:
            return self._error_result(48, "No page-date data available")

        if df_90d.empty:
            return self._error_result(
                48, "Need 90-day page-date data to identify new vs existing URLs"
            )

        df_90d = df_90d.copy()
        df_90d["date"] = pd.to_datetime(df_90d["date"])

        max_date = df_90d["date"].max()
        # Current period: last 30 days
        current_start = max_date - timedelta(days=29)
        # Previous period: 31-60 days ago
        prev_start = max_date - timedelta(days=59)
        prev_end = max_date - timedelta(days=30)

        current_df = df_90d[df_90d["date"] >= current_start]
        prev_df = df_90d[
            (df_90d["date"] >= prev_start) & (df_90d["date"] <= prev_end)
        ]

        if current_df.empty:
            return self._error_result(48, "No data in the current 30-day period")
        if prev_df.empty:
            return self._error_result(48, "No data in the previous 30-60 day period")

        current_urls = set(current_df["page"].unique())
        prev_urls = set(prev_df["page"].unique())

        new_urls = current_urls - prev_urls
        new_url_count = len(new_urls)
        total_current_urls = len(current_urls)

        # Calculate clicks from new URLs vs total clicks in current period
        current_clicks = current_df.groupby("page")["clicks"].sum().reset_index()
        total_clicks = current_clicks["clicks"].sum()

        new_url_clicks = current_clicks[
            current_clicks["page"].isin(new_urls)
        ]["clicks"].sum()

        new_url_click_share = (
            (new_url_clicks / total_clicks * 100) if total_clicks > 0 else 0.0
        )

        # Also compute new URL impression share for context
        current_impressions = current_df.groupby("page")["impressions"].sum().reset_index()
        total_impressions = current_impressions["impressions"].sum()
        new_url_impressions = current_impressions[
            current_impressions["page"].isin(new_urls)
        ]["impressions"].sum()
        new_url_imp_share = (
            (new_url_impressions / total_impressions * 100)
            if total_impressions > 0
            else 0.0
        )

        if new_url_click_share < 5:
            severity = Severity.HIGH
        elif new_url_click_share < 10:
            severity = Severity.MEDIUM
        elif new_url_click_share < 20:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        if new_url_count == 0:
            severity = Severity.HIGH
            trend = TrendDirection.DECLINING
        elif new_url_click_share < 5:
            trend = TrendDirection.DECLINING
        else:
            trend = TrendDirection.IMPROVING

        summary = (
            f"{new_url_count:,} new URLs appeared in the current 30-day period "
            f"(out of {total_current_urls:,} total). These new URLs captured "
            f"{new_url_click_share:.1f}% of clicks and {new_url_imp_share:.1f}% of impressions. "
            f"{'Low new URL click share suggests new content is not gaining traction quickly enough.' if new_url_click_share < 10 else 'New content is contributing meaningfully to overall traffic.'}"
        )

        # Build data table of new URLs ranked by clicks
        new_url_detail = current_df[current_df["page"].isin(new_urls)].groupby("page").agg(
            clicks=("clicks", "sum"),
            impressions=("impressions", "sum"),
        ).reset_index().sort_values("clicks", ascending=False)

        display_df = new_url_detail.head(25) if not new_url_detail.empty else None

        recommendations = []
        if new_url_click_share < 10:
            recommendations.extend([
                "Improve internal linking to new content to help it get discovered and indexed faster.",
                "Promote new URLs through social channels, newsletters, or link outreach to build initial traction.",
                "Ensure new content targets validated keyword opportunities with actual search demand.",
                "Review time-to-index for new URLs — slow indexing delays traffic acquisition.",
                "Evaluate whether new content quality and depth meet the standard of top-ranking competitors.",
            ])
        else:
            recommendations.append(
                "New content is gaining traction effectively. Maintain your publishing cadence "
                "and continue optimizing new URLs for target queries."
            )

        return self.create_result(
            metric_id=48,
            severity=severity,
            summary=summary,
            computed_value=round(new_url_click_share, 2),
            affected_count=new_url_count,
            data_table=display_df,
            recommendations=recommendations,
            trend_direction=trend,
            details={
                "new_urls": new_url_count,
                "total_current_urls": total_current_urls,
                "new_url_click_share_pct": round(new_url_click_share, 2),
                "new_url_impression_share_pct": round(new_url_imp_share, 2),
                "total_clicks": int(total_clicks),
                "new_url_clicks": int(new_url_clicks),
            },
        )
