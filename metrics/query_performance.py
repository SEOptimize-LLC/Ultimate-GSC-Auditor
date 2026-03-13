"""Query Performance metrics (1-12).

Analyzes query-level performance including counts, click rates,
position distributions, branded/non-branded ratios, and temporal
retention patterns.
"""

import logging
from datetime import timedelta
from typing import Optional

import pandas as pd

from metrics.base_metric import BaseMetricGroup
from models.metric_result import MetricResult, Severity, TrendDirection

logger = logging.getLogger(__name__)


class QueryPerformanceMetrics(BaseMetricGroup):
    """Metrics 1-12: Query Performance analysis."""

    METRIC_REGISTRY: dict[int, str] = {
        1: "metric_query_count_per_url",
        2: "metric_click_generating_query_rate",
        3: "metric_zero_click_query_count",
        4: "metric_top_3_query_share",
        5: "metric_top_10_query_share",
        6: "metric_striking_distance_query_count",
        7: "metric_position_21_50_query_count",
        8: "metric_branded_vs_non_branded_ratio",
        9: "metric_query_impression_share_per_url",
        10: "metric_query_retention_rate_mom",
        11: "metric_query_retention_rate_yoy",
        12: "metric_new_query_emergence_rate",
    }

    # ------------------------------------------------------------------ #
    # Metric 1 — Query Count per URL
    # ------------------------------------------------------------------ #
    def metric_query_count_per_url(self) -> MetricResult:
        """Total unique queries each URL appears for."""
        df = self.get_df("query_page_90d")
        if df.empty:
            return self._error_result(1, "No query-page data available")

        page_query_counts = (
            df.groupby("page")["query"]
            .nunique()
            .reset_index()
            .rename(columns={"query": "unique_queries"})
            .sort_values("unique_queries", ascending=True)
        )

        thin_pages = page_query_counts[page_query_counts["unique_queries"] < 5]
        total_pages = len(page_query_counts)
        thin_count = len(thin_pages)
        thin_pct = (thin_count / total_pages * 100) if total_pages > 0 else 0.0
        median_queries = page_query_counts["unique_queries"].median()

        # Severity based on % of pages with thin coverage
        if thin_pct >= 50:
            severity = Severity.HIGH
        elif thin_pct >= 30:
            severity = Severity.MEDIUM
        elif thin_pct >= 15:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        # Build data table — show the most affected pages
        display_df = thin_pages.head(25).copy() if not thin_pages.empty else page_query_counts.head(25).copy()

        summary = (
            f"{thin_count:,} of {total_pages:,} URLs ({thin_pct:.1f}%) have fewer "
            f"than 5 unique queries, indicating thin topical coverage. "
            f"Median queries per URL: {median_queries:.0f}."
        )

        recommendations = []
        if thin_pct >= 15:
            recommendations.extend([
                "Expand content depth on thin-coverage pages by targeting related subtopics and long-tail queries.",
                "Consider consolidating thin pages covering similar topics into a single, comprehensive resource.",
                "Add FAQ sections, how-to guides, or supporting content to attract more query variety.",
            ])
        else:
            recommendations.append(
                "Query coverage is healthy across most URLs. Monitor for pages losing query diversity over time."
            )

        return self.create_result(
            metric_id=1,
            severity=severity,
            summary=summary,
            computed_value=round(thin_pct, 2),
            affected_count=thin_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_pages": total_pages,
                "thin_pages": thin_count,
                "median_queries_per_url": float(median_queries),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 2 — Click-Generating Query Rate
    # ------------------------------------------------------------------ #
    def metric_click_generating_query_rate(self) -> MetricResult:
        """Percentage of a URL's queries that produced at least 1 click."""
        df = self.get_df("query_page_90d")
        if df.empty:
            return self._error_result(2, "No query-page data available")

        page_stats = df.groupby("page").agg(
            total_queries=("query", "nunique"),
            click_queries=("clicks", lambda x: (x > 0).sum()),
        ).reset_index()

        page_stats["click_rate_pct"] = (
            page_stats["click_queries"] / page_stats["total_queries"] * 100
        ).round(2)

        overall_rate = (
            page_stats["click_queries"].sum() / page_stats["total_queries"].sum() * 100
            if page_stats["total_queries"].sum() > 0
            else 0.0
        )

        # Find under-performers
        low_ctr_pages = page_stats[page_stats["click_rate_pct"] < 30].sort_values(
            "click_rate_pct", ascending=True
        )
        very_low_pages = page_stats[page_stats["click_rate_pct"] < 10]

        if overall_rate < 10:
            severity = Severity.CRITICAL
        elif overall_rate < 30:
            severity = Severity.HIGH
        elif overall_rate < 50:
            severity = Severity.MEDIUM
        elif overall_rate < 70:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"Overall click-generating query rate is {overall_rate:.1f}%. "
            f"{len(low_ctr_pages):,} URLs have rates below 30%, "
            f"and {len(very_low_pages):,} are below 10%. "
            f"Low rates indicate poor CTR or mismatched search intent."
        )

        recommendations = []
        if overall_rate < 50:
            recommendations.extend([
                "Review title tags and meta descriptions for low-performing URLs to improve click appeal.",
                "Analyze search intent alignment — the content may not match what users expect from the query.",
                "Check if SERP features (featured snippets, PAA) are absorbing clicks before users reach organic results.",
                "Consider improving content freshness and structured data to enhance listing visibility.",
            ])
        else:
            recommendations.append(
                "Click-generating rates are healthy. Continue monitoring for drops that may signal intent mismatches."
            )

        display_df = low_ctr_pages[["page", "total_queries", "click_queries", "click_rate_pct"]].head(25)

        return self.create_result(
            metric_id=2,
            severity=severity,
            summary=summary,
            computed_value=round(overall_rate, 2),
            affected_count=len(low_ctr_pages),
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "overall_rate": round(overall_rate, 2),
                "pages_below_30pct": len(low_ctr_pages),
                "pages_below_10pct": len(very_low_pages),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 3 — Zero-Click Query Count
    # ------------------------------------------------------------------ #
    def metric_zero_click_query_count(self) -> MetricResult:
        """Queries with impressions but zero clicks."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(3, "No query data available")

        total_queries = len(df)
        zero_click = df[(df["impressions"] > 0) & (df["clicks"] == 0)]
        zero_click_count = len(zero_click)
        zero_click_pct = (zero_click_count / total_queries * 100) if total_queries > 0 else 0.0

        # Total impressions wasted on zero-click queries
        wasted_impressions = zero_click["impressions"].sum()
        total_impressions = df["impressions"].sum()
        wasted_pct = (wasted_impressions / total_impressions * 100) if total_impressions > 0 else 0.0

        if zero_click_pct >= 70:
            severity = Severity.HIGH
        elif zero_click_pct >= 50:
            severity = Severity.MEDIUM
        elif zero_click_pct >= 30:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{zero_click_count:,} of {total_queries:,} queries ({zero_click_pct:.1f}%) "
            f"have impressions but zero clicks, accounting for {wasted_impressions:,} impressions "
            f"({wasted_pct:.1f}% of total). This may indicate SERP feature suppression, "
            f"poor rankings, or unappealing search snippets."
        )

        # Show top zero-click queries by impressions
        display_df = (
            zero_click
            .sort_values("impressions", ascending=False)
            [["query", "impressions", "position"]]
            .head(25)
        )

        recommendations = []
        if zero_click_pct >= 30:
            recommendations.extend([
                "Prioritize high-impression zero-click queries for title/description optimization to improve click-through.",
                "Check if Google is answering these queries directly via featured snippets, knowledge panels, or PAA boxes.",
                "Improve ranking positions for queries stuck on page 2+ — moving to page 1 significantly increases click probability.",
                "Add structured data (FAQ, HowTo) to win SERP features and increase visual prominence.",
            ])
        else:
            recommendations.append(
                "Zero-click rate is within normal range. Monitor for sudden increases that may indicate SERP feature changes."
            )

        return self.create_result(
            metric_id=3,
            severity=severity,
            summary=summary,
            computed_value=round(zero_click_pct, 2),
            affected_count=zero_click_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            opportunity_value=f"{wasted_impressions:,} impressions not generating clicks",
            details={
                "zero_click_queries": zero_click_count,
                "total_queries": total_queries,
                "wasted_impressions": int(wasted_impressions),
                "wasted_impression_pct": round(wasted_pct, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 4 — Top-3 Query Share
    # ------------------------------------------------------------------ #
    def metric_top_3_query_share(self) -> MetricResult:
        """Percentage of queries ranking in positions 1-3."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(4, "No query data available")

        total_queries = len(df)
        top_3 = df[df["position"] <= 3.0]
        top_3_count = len(top_3)
        top_3_pct = (top_3_count / total_queries * 100) if total_queries > 0 else 0.0

        # Clicks captured by top-3 queries
        top_3_clicks = top_3["clicks"].sum()
        total_clicks = df["clicks"].sum()
        top_3_click_share = (top_3_clicks / total_clicks * 100) if total_clicks > 0 else 0.0

        if top_3_pct >= 30:
            severity = Severity.INSIGHT
        elif top_3_pct >= 15:
            severity = Severity.LOW
        elif top_3_pct >= 5:
            severity = Severity.MEDIUM
        else:
            severity = Severity.HIGH

        summary = (
            f"{top_3_count:,} of {total_queries:,} queries ({top_3_pct:.1f}%) rank "
            f"in positions 1-3. These top positions capture {top_3_click_share:.1f}% "
            f"of total clicks. Higher share indicates stronger competitive positioning."
        )

        display_df = (
            top_3
            .sort_values("clicks", ascending=False)
            [["query", "clicks", "impressions", "position", "ctr"]]
            .head(25)
        )

        recommendations = []
        if top_3_pct < 15:
            recommendations.extend([
                "Focus link-building and content optimization on queries currently in positions 4-10 to push them into top 3.",
                "Analyze competitor content for top-3 queries to identify content gaps you can fill.",
                "Optimize on-page signals (title tags, headings, internal linking) for near-miss queries.",
            ])
        else:
            recommendations.append(
                "Top-3 query share is solid. Protect these rankings with regular content updates and strong internal linking."
            )

        return self.create_result(
            metric_id=4,
            severity=severity,
            summary=summary,
            computed_value=round(top_3_pct, 2),
            affected_count=top_3_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            benchmark_comparison="above" if top_3_pct >= 20 else "below",
            details={
                "top_3_queries": top_3_count,
                "total_queries": total_queries,
                "top_3_click_share": round(top_3_click_share, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 5 — Top-10 Query Share
    # ------------------------------------------------------------------ #
    def metric_top_10_query_share(self) -> MetricResult:
        """Percentage of queries ranking in positions 1-10 (page 1)."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(5, "No query data available")

        total_queries = len(df)
        top_10 = df[df["position"] <= 10.0]
        top_10_count = len(top_10)
        top_10_pct = (top_10_count / total_queries * 100) if total_queries > 0 else 0.0

        top_10_clicks = top_10["clicks"].sum()
        total_clicks = df["clicks"].sum()
        top_10_click_share = (top_10_clicks / total_clicks * 100) if total_clicks > 0 else 0.0

        if top_10_pct >= 50:
            severity = Severity.INSIGHT
        elif top_10_pct >= 30:
            severity = Severity.LOW
        elif top_10_pct >= 15:
            severity = Severity.MEDIUM
        else:
            severity = Severity.HIGH

        summary = (
            f"{top_10_count:,} of {total_queries:,} queries ({top_10_pct:.1f}%) rank "
            f"on page 1 (positions 1-10). These capture {top_10_click_share:.1f}% of "
            f"total clicks. Page 1 visibility is critical since ~95% of clicks go to page 1 results."
        )

        # Show distribution across position buckets
        not_page_1 = total_queries - top_10_count
        display_df = (
            top_10
            .sort_values("impressions", ascending=False)
            [["query", "clicks", "impressions", "position", "ctr"]]
            .head(25)
        )

        recommendations = []
        if top_10_pct < 30:
            recommendations.extend([
                "Prioritize content quality improvements for queries ranking on page 2 and beyond.",
                "Build topical authority through content clusters and internal linking to improve overall rankings.",
                "Conduct competitor analysis on page 1 results to understand what content attributes are rewarded.",
                "Review site-wide technical SEO factors that may be suppressing rankings (Core Web Vitals, mobile usability).",
            ])
        else:
            recommendations.append(
                "Page 1 query share is strong. Focus on moving page 1 queries from positions 4-10 into the top 3."
            )

        return self.create_result(
            metric_id=5,
            severity=severity,
            summary=summary,
            computed_value=round(top_10_pct, 2),
            affected_count=top_10_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            benchmark_comparison="above" if top_10_pct >= 40 else "below",
            details={
                "top_10_queries": top_10_count,
                "total_queries": total_queries,
                "off_page_1_queries": not_page_1,
                "top_10_click_share": round(top_10_click_share, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 6 — Striking Distance Query Count
    # ------------------------------------------------------------------ #
    def metric_striking_distance_query_count(self) -> MetricResult:
        """Queries ranking in positions 11-20 (quick-win targets)."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(6, "No query data available")

        total_queries = len(df)
        striking = df[(df["position"] > 10.0) & (df["position"] <= 20.0)]
        striking_count = len(striking)
        striking_pct = (striking_count / total_queries * 100) if total_queries > 0 else 0.0

        # Calculate potential impression/click opportunity
        striking_impressions = striking["impressions"].sum()

        # Severity is MEDIUM because these represent opportunities
        if striking_count >= 100:
            severity = Severity.MEDIUM
        elif striking_count >= 50:
            severity = Severity.MEDIUM
        elif striking_count >= 20:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{striking_count:,} queries ({striking_pct:.1f}%) are in striking distance "
            f"(positions 11-20) with {striking_impressions:,} total impressions. "
            f"These represent quick-win optimization targets — small ranking improvements "
            f"could move them to page 1."
        )

        display_df = (
            striking
            .sort_values("impressions", ascending=False)
            [["query", "impressions", "clicks", "position", "ctr"]]
            .head(25)
        )

        recommendations = [
            "Prioritize content optimization for striking-distance queries with the highest impression counts.",
            "Add internal links from authoritative pages to the ranking URLs for these queries.",
            "Improve on-page relevance by updating headings, adding relevant subtopics, and enhancing content depth.",
            "Build targeted backlinks to pages ranking for high-value striking-distance queries.",
            "Consider adding FAQ schema or additional structured data to improve SERP visibility.",
        ]

        return self.create_result(
            metric_id=6,
            severity=severity,
            summary=summary,
            computed_value=round(striking_pct, 2),
            affected_count=striking_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            opportunity_value=f"{striking_count:,} queries could be moved to page 1",
            details={
                "striking_distance_queries": striking_count,
                "total_queries": total_queries,
                "striking_impressions": int(striking_impressions),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 7 — Position 21-50 Query Count
    # ------------------------------------------------------------------ #
    def metric_position_21_50_query_count(self) -> MetricResult:
        """Queries ranking in positions 21-50 (mid-range growth opportunities)."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(7, "No query data available")

        total_queries = len(df)
        mid_range = df[(df["position"] > 20.0) & (df["position"] <= 50.0)]
        mid_count = len(mid_range)
        mid_pct = (mid_count / total_queries * 100) if total_queries > 0 else 0.0

        mid_impressions = mid_range["impressions"].sum()

        if mid_pct >= 40:
            severity = Severity.MEDIUM
        elif mid_pct >= 25:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{mid_count:,} queries ({mid_pct:.1f}%) rank in positions 21-50 "
            f"with {mid_impressions:,} total impressions. These are growth opportunities "
            f"that require more substantial effort (content expansion, link building) "
            f"to reach page 1."
        )

        display_df = (
            mid_range
            .sort_values("impressions", ascending=False)
            [["query", "impressions", "clicks", "position", "ctr"]]
            .head(25)
        )

        recommendations = []
        if mid_pct >= 25:
            recommendations.extend([
                "Create dedicated content clusters to build topical authority for mid-range query themes.",
                "Identify which mid-range queries have high search volume — these deserve focused content campaigns.",
                "Analyze whether content thinness or weak backlink profiles are holding these queries back.",
                "Consider creating supporting pillar/cluster content to boost authority for these topics.",
            ])
        else:
            recommendations.append(
                "Relatively few queries are stuck in the mid-range. Focus on striking-distance (11-20) queries for quicker wins."
            )

        return self.create_result(
            metric_id=7,
            severity=severity,
            summary=summary,
            computed_value=round(mid_pct, 2),
            affected_count=mid_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "mid_range_queries": mid_count,
                "total_queries": total_queries,
                "mid_range_impressions": int(mid_impressions),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 8 — Branded vs Non-Branded Query Ratio
    # ------------------------------------------------------------------ #
    def metric_branded_vs_non_branded_ratio(self) -> MetricResult:
        """Ratio of branded to total queries."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(8, "No query data available")

        total_queries = len(df)

        # Classify each query using the base class method
        df = df.copy()
        df["is_branded"] = df["query"].apply(self.is_branded_query)

        branded = df[df["is_branded"]]
        non_branded = df[~df["is_branded"]]
        branded_count = len(branded)
        non_branded_count = len(non_branded)
        branded_pct = (branded_count / total_queries * 100) if total_queries > 0 else 0.0

        # Click and impression distribution
        branded_clicks = branded["clicks"].sum()
        total_clicks = df["clicks"].sum()
        branded_click_pct = (branded_clicks / total_clicks * 100) if total_clicks > 0 else 0.0

        branded_impressions = branded["impressions"].sum()
        total_impressions = df["impressions"].sum()
        branded_imp_pct = (branded_impressions / total_impressions * 100) if total_impressions > 0 else 0.0

        # High branded reliance is a risk; too low may mean no brand awareness
        if branded_pct >= 70:
            severity = Severity.HIGH
        elif branded_pct >= 50:
            severity = Severity.MEDIUM
        elif branded_pct < 5 and self.brand_name:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        if branded_pct >= 50:
            assessment = (
                "Heavy reliance on branded queries means organic growth is limited. "
                "Non-branded query acquisition should be a priority."
            )
        elif branded_pct < 5 and self.brand_name:
            assessment = (
                "Very low branded query share may indicate weak brand recognition in search. "
                "Consider brand awareness campaigns."
            )
        else:
            assessment = (
                "Branded vs non-branded mix is healthy, indicating balanced organic reach."
            )

        summary = (
            f"{branded_count:,} branded queries ({branded_pct:.1f}%) vs "
            f"{non_branded_count:,} non-branded ({100 - branded_pct:.1f}%). "
            f"Branded queries account for {branded_click_pct:.1f}% of clicks "
            f"and {branded_imp_pct:.1f}% of impressions. {assessment}"
        )

        # Build data table showing top branded and non-branded queries
        top_branded = branded.nlargest(10, "clicks")[["query", "clicks", "impressions", "position"]].copy()
        top_branded["type"] = "branded"
        top_non_branded = non_branded.nlargest(15, "clicks")[["query", "clicks", "impressions", "position"]].copy()
        top_non_branded["type"] = "non-branded"
        display_df = pd.concat([top_branded, top_non_branded], ignore_index=True)

        recommendations = []
        if branded_pct >= 50:
            recommendations.extend([
                "Invest in non-branded content targeting informational and transactional queries relevant to your business.",
                "Build topical authority through comprehensive content hubs that attract organic non-branded traffic.",
                "Diversify your traffic sources to reduce dependency on brand-name searches.",
            ])
        elif branded_pct < 5 and self.brand_name:
            recommendations.extend([
                "Strengthen brand signals through consistent brand mentions, PR, and branded content.",
                "Ensure branded queries return the correct pages with optimized title tags.",
                "Consider if brand name visibility in SERPs is being suppressed by competitors or aggregators.",
            ])
        else:
            recommendations.append(
                "Branded/non-branded ratio is well-balanced. Continue growing non-branded organic reach while maintaining brand presence."
            )

        return self.create_result(
            metric_id=8,
            severity=severity,
            summary=summary,
            computed_value=round(branded_pct, 2),
            affected_count=branded_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "branded_queries": branded_count,
                "non_branded_queries": non_branded_count,
                "branded_click_share": round(branded_click_pct, 2),
                "branded_impression_share": round(branded_imp_pct, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 9 — Query Impression Share per URL
    # ------------------------------------------------------------------ #
    def metric_query_impression_share_per_url(self) -> MetricResult:
        """Percentage of total site impressions each URL accounts for."""
        df = self.get_df("query_page_90d")
        if df.empty:
            return self._error_result(9, "No query-page data available")

        total_impressions = df["impressions"].sum()
        if total_impressions == 0:
            return self._error_result(9, "No impressions recorded in data")

        page_impressions = (
            df.groupby("page")["impressions"]
            .sum()
            .reset_index()
            .rename(columns={"impressions": "total_impressions"})
        )
        page_impressions["impression_share_pct"] = (
            page_impressions["total_impressions"] / total_impressions * 100
        ).round(2)
        page_impressions = page_impressions.sort_values("impression_share_pct", ascending=False)

        # Check concentration — if top 5 pages hold >50% of impressions
        top_5_share = page_impressions.head(5)["impression_share_pct"].sum()
        top_10_share = page_impressions.head(10)["impression_share_pct"].sum()
        total_pages = len(page_impressions)

        if top_5_share >= 70:
            severity = Severity.HIGH
        elif top_5_share >= 50:
            severity = Severity.MEDIUM
        elif top_5_share >= 35:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"Top 5 URLs account for {top_5_share:.1f}% of total impressions, "
            f"and top 10 account for {top_10_share:.1f}%. "
            f"Total: {total_pages:,} pages with {total_impressions:,} impressions. "
            f"{'High concentration creates risk if top pages lose rankings.' if top_5_share >= 50 else 'Impression distribution is reasonably balanced.'}"
        )

        display_df = page_impressions[["page", "total_impressions", "impression_share_pct"]].head(25)

        recommendations = []
        if top_5_share >= 50:
            recommendations.extend([
                "Diversify content investment — over-reliance on a few pages creates fragility if rankings shift.",
                "Identify underperforming pages and optimize them to earn a larger share of impressions.",
                "Build supporting content that links to and reinforces your top-performing pages.",
                "Monitor top-impression pages closely for ranking drops that could dramatically impact traffic.",
            ])
        else:
            recommendations.append(
                "Impression share is well-distributed. Continue building content breadth to maintain balanced visibility."
            )

        return self.create_result(
            metric_id=9,
            severity=severity,
            summary=summary,
            computed_value=round(top_5_share, 2),
            affected_count=total_pages,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "top_5_impression_share": round(top_5_share, 2),
                "top_10_impression_share": round(top_10_share, 2),
                "total_pages": total_pages,
                "total_impressions": int(total_impressions),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 10 — Query Retention Rate (MoM)
    # ------------------------------------------------------------------ #
    def metric_query_retention_rate_mom(self) -> MetricResult:
        """Percentage of queries from prior month still ranking this month."""
        df_90d = self.get_df("query_date_90d")
        df_30d = self.get_df("query_date_30d")

        if df_90d.empty and df_30d.empty:
            return self._error_result(10, "No temporal query data available")

        # Use 90d data split into months if 30d is unavailable or as cross-check
        # Strategy: derive current month and previous month from the 90d data
        if df_90d.empty:
            return self._error_result(10, "Need 90-day query-date data for MoM comparison")

        df_90d = df_90d.copy()
        df_90d["date"] = pd.to_datetime(df_90d["date"])

        max_date = df_90d["date"].max()
        # Current month: last 30 days
        current_start = max_date - timedelta(days=29)
        # Previous month: 31-60 days ago
        prev_start = max_date - timedelta(days=59)
        prev_end = max_date - timedelta(days=30)

        current_queries = set(
            df_90d[df_90d["date"] >= current_start]["query"].unique()
        )
        prev_queries = set(
            df_90d[(df_90d["date"] >= prev_start) & (df_90d["date"] <= prev_end)]["query"].unique()
        )

        if not prev_queries:
            return self._error_result(10, "No queries found in the previous month period")

        retained = current_queries & prev_queries
        retained_count = len(retained)
        prev_count = len(prev_queries)
        current_count = len(current_queries)
        retention_rate = (retained_count / prev_count * 100) if prev_count > 0 else 0.0

        lost_queries = prev_queries - current_queries
        lost_count = len(lost_queries)

        if retention_rate < 50:
            severity = Severity.HIGH
        elif retention_rate < 70:
            severity = Severity.MEDIUM
        elif retention_rate < 85:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        # Determine trend
        if retention_rate >= 85:
            trend = TrendDirection.STABLE
        elif retention_rate >= 70:
            trend = TrendDirection.DECLINING
        else:
            trend = TrendDirection.DECLINING

        summary = (
            f"Query retention rate (MoM) is {retention_rate:.1f}%. "
            f"{retained_count:,} of {prev_count:,} previous-month queries are "
            f"still ranking, while {lost_count:,} queries were lost. "
            f"Current month has {current_count:,} unique queries."
        )

        # Build data table of lost queries if we can find impression data for them
        lost_query_data = df_90d[
            (df_90d["query"].isin(lost_queries))
            & (df_90d["date"] >= prev_start)
            & (df_90d["date"] <= prev_end)
        ]
        if not lost_query_data.empty:
            display_df = (
                lost_query_data
                .groupby("query")
                .agg({"impressions": "sum", "clicks": "sum"})
                .reset_index()
                .sort_values("impressions", ascending=False)
                .head(25)
            )
            display_df["status"] = "lost"
        else:
            display_df = None

        recommendations = []
        if retention_rate < 70:
            recommendations.extend([
                "Investigate lost queries to determine if rankings dropped or content was de-indexed.",
                "Check for algorithm updates during the comparison period that may have impacted rankings.",
                "Review content freshness — outdated content often loses rankings to newer, more relevant pages.",
                "Strengthen internal linking to pages that lost query visibility.",
            ])
        elif retention_rate < 85:
            recommendations.extend([
                "Monitor lost queries for patterns (e.g., specific topics, URL groups) to identify systemic issues.",
                "Regularly update and refresh content to maintain query diversity and rankings.",
            ])
        else:
            recommendations.append(
                "Query retention is strong. Continue maintaining content freshness and monitoring for early signs of decay."
            )

        return self.create_result(
            metric_id=10,
            severity=severity,
            summary=summary,
            computed_value=round(retention_rate, 2),
            affected_count=lost_count,
            data_table=display_df,
            recommendations=recommendations,
            trend_direction=trend,
            details={
                "retained_queries": retained_count,
                "lost_queries": lost_count,
                "previous_month_queries": prev_count,
                "current_month_queries": current_count,
                "retention_rate": round(retention_rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 11 — Query Retention Rate (YoY)
    # ------------------------------------------------------------------ #
    def metric_query_retention_rate_yoy(self) -> MetricResult:
        """Percentage of queries from same period last year still ranking."""
        df_90d = self.get_df("query_date_90d")
        df_365d = self.get_df("query_date_365d")

        if df_90d.empty:
            return self._error_result(11, "No current 90-day query-date data available")
        if df_365d.empty:
            return self._error_result(11, "No 365-day query-date data available for YoY comparison")

        df_90d = df_90d.copy()
        df_365d = df_365d.copy()
        df_90d["date"] = pd.to_datetime(df_90d["date"])
        df_365d["date"] = pd.to_datetime(df_365d["date"])

        # Current period: last 90 days
        current_queries = set(df_90d["query"].unique())

        # Same period last year: from the 365d data, take the window that is
        # approximately 365-274 to 365 days ago (a 90-day window 1 year back)
        max_date_365 = df_365d["date"].max()
        yoy_end = max_date_365 - timedelta(days=275)  # ~9 months ago ≈ start of same period last year
        yoy_start = yoy_end - timedelta(days=89)

        last_year_queries = set(
            df_365d[
                (df_365d["date"] >= yoy_start) & (df_365d["date"] <= yoy_end)
            ]["query"].unique()
        )

        if not last_year_queries:
            return self._error_result(
                11, "No queries found in the same period last year. The 365-day data may not cover that range."
            )

        retained = current_queries & last_year_queries
        retained_count = len(retained)
        last_year_count = len(last_year_queries)
        current_count = len(current_queries)
        retention_rate = (retained_count / last_year_count * 100) if last_year_count > 0 else 0.0

        lost_count = len(last_year_queries - current_queries)
        new_count = len(current_queries - last_year_queries)

        if retention_rate < 40:
            severity = Severity.HIGH
        elif retention_rate < 60:
            severity = Severity.MEDIUM
        elif retention_rate < 75:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        if retention_rate >= 75:
            trend = TrendDirection.STABLE
        elif retention_rate >= 50:
            trend = TrendDirection.DECLINING
        else:
            trend = TrendDirection.DECLINING

        summary = (
            f"Year-over-year query retention is {retention_rate:.1f}%. "
            f"{retained_count:,} of {last_year_count:,} queries from the same period "
            f"last year are still ranking. {lost_count:,} queries were lost, while "
            f"{new_count:,} new queries emerged. Current period has {current_count:,} unique queries."
        )

        recommendations = []
        if retention_rate < 60:
            recommendations.extend([
                "Major query turnover suggests significant ranking shifts — investigate algorithm updates and competitor movements.",
                "Audit lost queries to identify pages that experienced content decay or technical issues.",
                "Refresh high-value evergreen content that may have lost relevance over the past year.",
                "Evaluate whether site architecture changes or URL migrations contributed to query loss.",
            ])
        elif retention_rate < 75:
            recommendations.extend([
                "Moderate query churn is normal but worth monitoring. Focus on retaining high-value queries.",
                "Implement a content refresh calendar to proactively update aging content before it loses rankings.",
            ])
        else:
            recommendations.append(
                "YoY query retention is healthy, indicating strong content durability. Continue regular content maintenance."
            )

        return self.create_result(
            metric_id=11,
            severity=severity,
            summary=summary,
            computed_value=round(retention_rate, 2),
            affected_count=lost_count,
            recommendations=recommendations,
            trend_direction=trend,
            details={
                "retained_queries": retained_count,
                "lost_queries": lost_count,
                "new_queries": new_count,
                "last_year_queries": last_year_count,
                "current_queries": current_count,
                "retention_rate": round(retention_rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 12 — New Query Emergence Rate
    # ------------------------------------------------------------------ #
    def metric_new_query_emergence_rate(self) -> MetricResult:
        """Percentage of queries appearing for the first time this period."""
        df_90d = self.get_df("query_date_90d")
        df_30d = self.get_df("query_date_30d")

        if df_90d.empty:
            return self._error_result(12, "No 90-day query-date data available")

        df_90d = df_90d.copy()
        df_90d["date"] = pd.to_datetime(df_90d["date"])

        max_date = df_90d["date"].max()

        # Current period: last 30 days
        current_start = max_date - timedelta(days=29)
        # Historical period: 31-90 days ago
        hist_end = max_date - timedelta(days=30)

        current_queries = set(
            df_90d[df_90d["date"] >= current_start]["query"].unique()
        )
        historical_queries = set(
            df_90d[df_90d["date"] <= hist_end]["query"].unique()
        )

        if not current_queries:
            return self._error_result(12, "No queries found in the current 30-day period")

        new_queries = current_queries - historical_queries
        new_count = len(new_queries)
        current_count = len(current_queries)
        emergence_rate = (new_count / current_count * 100) if current_count > 0 else 0.0

        # Get details on new queries
        new_query_details = df_90d[
            (df_90d["query"].isin(new_queries))
            & (df_90d["date"] >= current_start)
        ]
        if not new_query_details.empty:
            new_query_summary = (
                new_query_details
                .groupby("query")
                .agg({"impressions": "sum", "clicks": "sum"})
                .reset_index()
                .sort_values("impressions", ascending=False)
            )
            new_query_impressions = new_query_summary["impressions"].sum()
            new_query_clicks = new_query_summary["clicks"].sum()
            display_df = new_query_summary.head(25).copy()
            display_df["status"] = "new"
        else:
            new_query_impressions = 0
            new_query_clicks = 0
            display_df = None

        # Higher emergence rate is generally positive (growing visibility)
        if emergence_rate >= 30:
            severity = Severity.INSIGHT
            trend = TrendDirection.IMPROVING
        elif emergence_rate >= 15:
            severity = Severity.INSIGHT
            trend = TrendDirection.IMPROVING
        elif emergence_rate >= 5:
            severity = Severity.LOW
            trend = TrendDirection.STABLE
        else:
            severity = Severity.MEDIUM
            trend = TrendDirection.DECLINING

        summary = (
            f"{new_count:,} new queries ({emergence_rate:.1f}%) appeared in the last "
            f"30 days that were not present in the prior 60 days. These new queries "
            f"generated {new_query_impressions:,} impressions and {new_query_clicks:,} clicks. "
            f"{'Strong query emergence indicates growing topical reach.' if emergence_rate >= 15 else 'Low emergence rate may indicate stagnating content visibility.'}"
        )

        recommendations = []
        if emergence_rate < 5:
            recommendations.extend([
                "Publish new content targeting trending and emerging topics in your niche.",
                "Update existing content to target related long-tail queries you have not yet captured.",
                "Analyze competitors for new queries they rank for that you are missing.",
                "Explore seasonal or trending topics to capture timely search demand.",
            ])
        elif emergence_rate < 15:
            recommendations.extend([
                "Continue publishing fresh content but consider increasing cadence or topical breadth.",
                "Leverage high-performing new queries by creating dedicated, in-depth content around them.",
            ])
        else:
            recommendations.append(
                "New query emergence is healthy, indicating growing organic reach. Double down on the topics driving new queries."
            )

        return self.create_result(
            metric_id=12,
            severity=severity,
            summary=summary,
            computed_value=round(emergence_rate, 2),
            affected_count=new_count,
            data_table=display_df,
            recommendations=recommendations,
            trend_direction=trend,
            opportunity_value=f"{new_count:,} new queries discovered",
            details={
                "new_queries": new_count,
                "current_period_queries": current_count,
                "historical_queries": len(historical_queries),
                "new_query_impressions": int(new_query_impressions),
                "new_query_clicks": int(new_query_clicks),
                "emergence_rate": round(emergence_rate, 2),
            },
        )
