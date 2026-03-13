"""Content Portfolio & Library Health metrics (95-100).

Analyzes the overall health and efficiency of the site's content library
including active/dead-weight URL rates, cannibalization clusters,
new content traction, consolidation opportunities, and traffic concentration.
"""

import logging
from datetime import timedelta
from typing import Optional
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from metrics.base_metric import BaseMetricGroup
from models.metric_result import MetricResult, Severity, TrendDirection

logger = logging.getLogger(__name__)


class ContentPortfolioMetrics(BaseMetricGroup):
    """Metrics 95-100: Content Portfolio & Library Health analysis."""

    METRIC_REGISTRY: dict[int, str] = {
        95: "metric_active_url_rate",
        96: "metric_dead_weight_url_rate",
        97: "metric_content_cannibalization_cluster_count",
        98: "metric_new_content_traction_rate",
        99: "metric_content_consolidation_opportunity_rate",
        100: "metric_top_10_pct_url_traffic_concentration",
    }

    # ------------------------------------------------------------------ #
    # Helper — extract first path segment as proxy cluster
    # ------------------------------------------------------------------ #
    def _get_url_directory(self, url: str) -> str:
        """Extract the first URL path segment as a proxy topic cluster.

        Examples:
            https://example.com/blog/my-post  -> /blog
            https://example.com/products/shoes -> /products
            https://example.com/               -> /
        """
        try:
            parsed = urlparse(url)
            path = parsed.path.strip("/")
            if not path:
                return "/"
            first_segment = path.split("/")[0]
            return f"/{first_segment}"
        except Exception:
            return "/unknown"

    def _resolve_cluster(self, query: str, page: str) -> str:
        """Resolve a topic cluster for a query-page pair.

        Uses AI-based topic cluster from self.get_topic_cluster() when
        available, otherwise falls back to the first URL path segment.
        """
        ai_cluster = self.get_topic_cluster(query)
        if ai_cluster:
            return ai_cluster
        return self._get_url_directory(page)

    # ------------------------------------------------------------------ #
    # Metric 95 — Active URL Rate
    # ------------------------------------------------------------------ #
    def metric_active_url_rate(self) -> MetricResult:
        """Percentage of total known URLs that are actively receiving clicks."""
        df_90d = self.get_df("page_90d")
        df_365d = self.get_df("page_365d")

        if df_365d.empty:
            return self._error_result(95, "No 365-day page data available")

        # Full URL universe from the 365d window
        all_urls_365d = set(df_365d["page"].unique())
        total_365d_count = len(all_urls_365d)

        if total_365d_count == 0:
            return self._error_result(95, "No URLs found in 365-day data")

        # Active URLs: present in 90d data with clicks > 0
        if df_90d.empty:
            active_count = 0
            active_urls = set()
        else:
            active_df = df_90d[df_90d["clicks"] > 0]
            active_urls = set(active_df["page"].unique())
            active_count = len(active_urls)

        active_rate = (active_count / total_365d_count * 100) if total_365d_count > 0 else 0.0
        inactive_count = total_365d_count - active_count

        # Severity thresholds
        if active_rate < 30:
            severity = Severity.CRITICAL
        elif active_rate < 50:
            severity = Severity.HIGH
        elif active_rate < 70:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{active_count:,} of {total_365d_count:,} known URLs ({active_rate:.1f}%) "
            f"are actively generating clicks in the last 90 days. "
            f"{inactive_count:,} URLs have zero clicks, indicating a large portion of "
            f"the content library may not be contributing to organic traffic."
            if active_rate < 70
            else f"{active_count:,} of {total_365d_count:,} known URLs ({active_rate:.1f}%) "
            f"are actively generating clicks in the last 90 days. "
            f"The content library is performing well with a healthy active URL ratio."
        )

        # Build data table: show active URLs sorted by clicks (top performers)
        if not df_90d.empty and active_count > 0:
            active_table = (
                active_df
                .sort_values("clicks", ascending=False)
                [["page", "clicks", "impressions", "ctr", "position"]]
                .head(25)
                .copy()
            )
            active_table["status"] = "active"
            display_df = active_table
        else:
            display_df = None

        recommendations = []
        if active_rate < 50:
            recommendations.extend([
                "Audit inactive URLs and determine whether to update, consolidate, or remove them.",
                "Prioritize content refresh for high-potential inactive pages that previously generated traffic.",
                "Implement a content pruning strategy — redirect or noindex URLs that add no search value.",
                "Review internal linking to ensure inactive content is not orphaned from the site structure.",
            ])
        elif active_rate < 70:
            recommendations.extend([
                "Schedule regular content audits to identify and revitalize underperforming URLs.",
                "Consider consolidating thin or overlapping inactive pages into stronger, comprehensive resources.",
                "Improve internal linking to distribute authority to pages that currently lack visibility.",
            ])
        else:
            recommendations.append(
                "Active URL rate is healthy. Continue monitoring for drift and schedule quarterly content audits."
            )

        return self.create_result(
            metric_id=95,
            severity=severity,
            summary=summary,
            computed_value=round(active_rate, 2),
            affected_count=active_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "active_urls": active_count,
                "inactive_urls": inactive_count,
                "total_urls_365d": total_365d_count,
                "active_rate_pct": round(active_rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 96 — Dead Weight URL Rate
    # ------------------------------------------------------------------ #
    def metric_dead_weight_url_rate(self) -> MetricResult:
        """Percentage of URLs with zero clicks in the recent 90-day window."""
        df_90d = self.get_df("page_90d")
        df_365d = self.get_df("page_365d")

        if df_365d.empty:
            return self._error_result(96, "No 365-day page data available")

        all_urls_365d = set(df_365d["page"].unique())
        total_365d_count = len(all_urls_365d)

        if total_365d_count == 0:
            return self._error_result(96, "No URLs found in 365-day data")

        # Dead weight: URLs in 365d that have 0 clicks in 90d OR are not present at all
        if df_90d.empty:
            # All URLs are dead weight if there's no 90d data
            dead_weight_urls = all_urls_365d
        else:
            urls_with_clicks_90d = set(
                df_90d[df_90d["clicks"] > 0]["page"].unique()
            )
            dead_weight_urls = all_urls_365d - urls_with_clicks_90d

        dead_count = len(dead_weight_urls)
        dead_rate = (dead_count / total_365d_count * 100) if total_365d_count > 0 else 0.0

        # Calculate wasted impressions on dead weight URLs
        wasted_impressions = 0
        if not df_90d.empty:
            dead_in_90d = df_90d[df_90d["page"].isin(dead_weight_urls)]
            wasted_impressions = int(dead_in_90d["impressions"].sum())

        # Severity thresholds
        if dead_rate > 60:
            severity = Severity.CRITICAL
        elif dead_rate > 40:
            severity = Severity.HIGH
        elif dead_rate > 25:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{dead_count:,} of {total_365d_count:,} URLs ({dead_rate:.1f}%) are dead weight — "
            f"they generated zero clicks in the last 90 days. "
            f"These URLs consumed {wasted_impressions:,} impressions without delivering traffic. "
            f"{'This represents a significant crawl budget and content quality concern.' if dead_rate > 40 else 'A moderate proportion of the content library is underperforming.'}"
            if dead_rate > 25
            else f"{dead_count:,} of {total_365d_count:,} URLs ({dead_rate:.1f}%) are dead weight — "
            f"zero clicks in the last 90 days. The content library is efficiently earning traffic."
        )

        # Build data table: show dead-weight URLs with impressions (wasted potential)
        if not df_90d.empty:
            dead_detail = (
                df_90d[df_90d["page"].isin(dead_weight_urls)]
                .sort_values("impressions", ascending=False)
                [["page", "impressions", "clicks", "position"]]
                .head(25)
                .copy()
            )
            dead_detail["status"] = "dead_weight"
            display_df = dead_detail if not dead_detail.empty else None
        else:
            # Show URLs from 365d that are entirely absent from 90d
            dead_list = pd.DataFrame({"page": list(dead_weight_urls)})
            dead_list["status"] = "absent_from_90d"
            display_df = dead_list.head(25)

        recommendations = []
        if dead_rate > 40:
            recommendations.extend([
                "Conduct a comprehensive content audit to classify dead-weight URLs by salvageability.",
                "Redirect or remove URLs that serve no search purpose and dilute crawl budget.",
                "Refresh high-impression dead-weight pages with updated content, improved titles, and better CTAs.",
                "Consolidate overlapping dead-weight pages into fewer, stronger resources.",
                "Review robots.txt and sitemap to ensure dead-weight URLs are not consuming crawl budget unnecessarily.",
            ])
        elif dead_rate > 25:
            recommendations.extend([
                "Identify dead-weight URLs with high impressions — these have visibility but fail to convert to clicks.",
                "Prioritize content refresh for pages that previously generated traffic but have decayed.",
                "Consider noindexing or redirecting truly obsolete pages.",
            ])
        else:
            recommendations.append(
                "Dead weight rate is within a healthy range. Continue quarterly content pruning to maintain efficiency."
            )

        return self.create_result(
            metric_id=96,
            severity=severity,
            summary=summary,
            computed_value=round(dead_rate, 2),
            affected_count=dead_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "dead_weight_urls": dead_count,
                "total_urls_365d": total_365d_count,
                "dead_weight_rate_pct": round(dead_rate, 2),
                "wasted_impressions": wasted_impressions,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 97 — Content Cannibalization Cluster Count
    # ------------------------------------------------------------------ #
    def metric_content_cannibalization_cluster_count(self) -> MetricResult:
        """Count of topic clusters where multiple pages compete for the same queries."""
        df_90d = self.get_df("query_page_90d")
        df_365d = self.get_df("query_page_365d")

        if df_90d.empty and df_365d.empty:
            return self._error_result(97, "No query-page data available")

        # Prefer 90d data; fall back to 365d
        df = df_90d if not df_90d.empty else df_365d

        # Step 1: Assign each row a topic cluster
        df = df.copy()
        df["cluster"] = df.apply(
            lambda row: self._resolve_cluster(row["query"], row["page"]),
            axis=1,
        )

        # Step 2: Within each cluster, find queries that appear on 2+ distinct pages
        cluster_query_pages = (
            df.groupby(["cluster", "query"])["page"]
            .nunique()
            .reset_index()
            .rename(columns={"page": "page_count"})
        )
        cannibalized_pairs = cluster_query_pages[cluster_query_pages["page_count"] >= 2]

        # Step 3: Count clusters that have at least one cannibalized query
        total_clusters = df["cluster"].nunique()
        if total_clusters == 0:
            return self._error_result(97, "No topic clusters could be identified")

        clusters_with_cannibalization = cannibalized_pairs["cluster"].nunique()
        cannibalization_rate = (
            clusters_with_cannibalization / total_clusters * 100
        ) if total_clusters > 0 else 0.0

        # Total cannibalized queries across all clusters
        total_cannibalized_queries = cannibalized_pairs["query"].nunique()

        # Severity based on % of clusters affected
        if cannibalization_rate > 40:
            severity = Severity.HIGH
        elif cannibalization_rate > 25:
            severity = Severity.MEDIUM
        elif cannibalization_rate > 10:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{clusters_with_cannibalization} of {total_clusters} topic clusters "
            f"({cannibalization_rate:.1f}%) exhibit content cannibalization, "
            f"where 2+ pages compete for the same queries. "
            f"{total_cannibalized_queries:,} unique queries are cannibalized across these clusters. "
            f"{'This widespread cannibalization likely dilutes ranking authority and confuses search engines.' if cannibalization_rate > 40 else 'Some cannibalization is normal, but affected clusters should be reviewed.'}"
        )

        # Build data table: show the most cannibalized queries with cluster and page count
        display_df = (
            cannibalized_pairs
            .sort_values("page_count", ascending=False)
            [["cluster", "query", "page_count"]]
            .head(25)
            .copy()
        )
        display_df.rename(columns={"page_count": "competing_pages"}, inplace=True)

        recommendations = []
        if cannibalization_rate > 25:
            recommendations.extend([
                "Identify the strongest page in each cannibalized cluster and consolidate weaker pages into it.",
                "Use 301 redirects to merge duplicate-intent pages and consolidate ranking signals.",
                "Differentiate page focus within clusters — assign distinct query targets to each page.",
                "Strengthen internal linking to signal to search engines which page should rank for each query.",
                "Consider adding canonical tags where content overlap is intentional.",
            ])
        elif cannibalization_rate > 10:
            recommendations.extend([
                "Review cannibalized clusters and determine if pages serve distinct user intents.",
                "For clusters with true overlap, consolidate content into a single authoritative page.",
                "Improve internal linking to clarify which page is the primary target for each query.",
            ])
        else:
            recommendations.append(
                "Cannibalization is minimal. Monitor clusters periodically as new content is published."
            )

        return self.create_result(
            metric_id=97,
            severity=severity,
            summary=summary,
            computed_value=round(cannibalization_rate, 2),
            affected_count=clusters_with_cannibalization,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "total_clusters": total_clusters,
                "clusters_with_cannibalization": clusters_with_cannibalization,
                "cannibalization_rate_pct": round(cannibalization_rate, 2),
                "total_cannibalized_queries": total_cannibalized_queries,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 98 — New Content Traction Rate
    # ------------------------------------------------------------------ #
    def metric_new_content_traction_rate(self) -> MetricResult:
        """Percentage of newly published URLs that are generating clicks."""
        df_90d = self.get_df("page_date_90d")
        df_30d = self.get_df("page_date_30d")

        if df_90d.empty and df_30d.empty:
            return self._error_result(98, "No page-date data available")

        # Use 90d data to derive time windows
        # If 30d data is available, use it for the recent window; otherwise slice from 90d
        if not df_90d.empty:
            df = df_90d.copy()
            df["date"] = pd.to_datetime(df["date"])
            max_date = df["date"].max()
        elif not df_30d.empty:
            df = df_30d.copy()
            df["date"] = pd.to_datetime(df["date"])
            max_date = df["date"].max()
        else:
            return self._error_result(98, "No date-level page data available")

        # Define time windows
        # Recent window: last 30 days
        recent_start = max_date - timedelta(days=29)
        # Prior window: 30-60 days ago
        prior_start = max_date - timedelta(days=59)
        prior_end = max_date - timedelta(days=30)

        # URLs in the recent 30-day window
        recent_df = df[df["date"] >= recent_start]
        recent_urls = set(recent_df["page"].unique())

        # URLs in the prior 30-60 day window
        prior_df = df[(df["date"] >= prior_start) & (df["date"] <= prior_end)]
        prior_urls = set(prior_df["page"].unique())

        # New content: appears in last 30d but NOT in prior 30-60d
        new_urls = recent_urls - prior_urls
        new_count = len(new_urls)

        if new_count == 0:
            return self.create_result(
                metric_id=98,
                severity=Severity.INSIGHT,
                summary=(
                    "No new URLs were detected in the last 30 days compared to the "
                    "prior 30-60 day period. This may indicate a content publishing "
                    "pause or that all recent URLs were already present."
                ),
                computed_value=0.0,
                affected_count=0,
                recommendations=[
                    "Ensure new content is being published regularly to maintain organic growth.",
                    "Check if new pages are being indexed — they may exist but not appear in Search Console data yet.",
                ],
                details={
                    "new_urls": 0,
                    "total_recent_urls": len(recent_urls),
                    "total_prior_urls": len(prior_urls),
                },
            )

        # Of the new URLs, how many have clicks > 0 in the recent window?
        new_url_recent_data = recent_df[recent_df["page"].isin(new_urls)]
        new_url_clicks = (
            new_url_recent_data
            .groupby("page")
            .agg(total_clicks=("clicks", "sum"), total_impressions=("impressions", "sum"))
            .reset_index()
        )

        urls_with_clicks = new_url_clicks[new_url_clicks["total_clicks"] > 0]
        traction_count = len(urls_with_clicks)
        traction_rate = (traction_count / new_count * 100) if new_count > 0 else 0.0

        # Aggregate click share of new content
        total_site_clicks = recent_df["clicks"].sum()
        new_content_clicks = urls_with_clicks["total_clicks"].sum() if not urls_with_clicks.empty else 0
        new_content_click_share = (
            new_content_clicks / total_site_clicks * 100
        ) if total_site_clicks > 0 else 0.0

        # Severity
        if traction_rate < 30:
            severity = Severity.MEDIUM
        elif traction_rate < 50:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{traction_count} of {new_count} new URLs ({traction_rate:.1f}%) are "
            f"generating clicks within their first 30 days. "
            f"New content accounts for {new_content_click_share:.1f}% of total site clicks "
            f"({int(new_content_clicks):,} clicks). "
            f"{'Low traction suggests new content is not meeting search demand or needs time to mature.' if traction_rate < 50 else 'New content is gaining traction at a healthy rate.'}"
        )

        # Build data table: show new URLs sorted by clicks
        display_df = (
            new_url_clicks
            .sort_values("total_clicks", ascending=False)
            [["page", "total_clicks", "total_impressions"]]
            .head(25)
            .copy()
        )
        display_df["is_new"] = True

        recommendations = []
        if traction_rate < 30:
            recommendations.extend([
                "Review the topic selection and keyword targeting for newly published content.",
                "Ensure new pages are properly internally linked and included in the sitemap.",
                "Check indexation status of new URLs — they may not yet be crawled or indexed by Google.",
                "Improve content quality and depth to better match search intent for target queries.",
                "Promote new content through internal banners, newsletter mentions, or social sharing to accelerate discovery.",
            ])
        elif traction_rate < 50:
            recommendations.extend([
                "Analyze which new content types and topics gain traction fastest and replicate those patterns.",
                "Strengthen internal linking to new content from high-authority existing pages.",
                "Monitor new content indexation speed and request indexing for slow-to-index URLs.",
            ])
        else:
            recommendations.append(
                "New content traction is strong. Continue the current content strategy and monitor time-to-traction trends."
            )

        return self.create_result(
            metric_id=98,
            severity=severity,
            summary=summary,
            computed_value=round(traction_rate, 2),
            affected_count=new_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "new_urls": new_count,
                "urls_with_clicks": traction_count,
                "traction_rate_pct": round(traction_rate, 2),
                "new_content_total_clicks": int(new_content_clicks),
                "new_content_click_share_pct": round(new_content_click_share, 2),
                "total_recent_urls": len(recent_urls),
                "total_prior_urls": len(prior_urls),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 99 — Content Consolidation Opportunity Rate
    # ------------------------------------------------------------------ #
    def metric_content_consolidation_opportunity_rate(self) -> MetricResult:
        """Percentage of multi-page queries where no single page dominates clicks."""
        df = self.get_df("query_page_90d")
        if df.empty:
            return self._error_result(99, "No query-page data available")

        # Step 1: Find queries that rank on 2+ pages
        query_page_counts = (
            df.groupby("query")["page"]
            .nunique()
            .reset_index()
            .rename(columns={"page": "page_count"})
        )
        multi_page_queries = query_page_counts[query_page_counts["page_count"] >= 2]
        multi_page_query_set = set(multi_page_queries["query"])
        total_multi_page = len(multi_page_query_set)

        if total_multi_page == 0:
            return self.create_result(
                metric_id=99,
                severity=Severity.INSIGHT,
                summary=(
                    "No queries were found ranking on multiple pages. "
                    "Each query maps to a single URL, indicating clean content targeting."
                ),
                computed_value=0.0,
                affected_count=0,
                recommendations=[
                    "Content targeting is well-organized. Monitor for emerging overlap as new content is published."
                ],
                details={
                    "multi_page_queries": 0,
                    "total_queries": len(query_page_counts),
                },
            )

        # Step 2: For each multi-page query, check if any single page has >= 50% of clicks
        multi_df = df[df["query"].isin(multi_page_query_set)].copy()

        # Calculate click share per page for each query
        query_total_clicks = (
            multi_df.groupby("query")["clicks"]
            .sum()
            .reset_index()
            .rename(columns={"clicks": "total_query_clicks"})
        )
        multi_df = multi_df.merge(query_total_clicks, on="query", how="left")

        # Avoid division by zero: for queries with 0 total clicks, every page has 0 share
        multi_df["click_share"] = multi_df.apply(
            lambda row: (
                row["clicks"] / row["total_query_clicks"] * 100
                if row["total_query_clicks"] > 0
                else 0.0
            ),
            axis=1,
        )

        # Find the max click share per query
        max_share_per_query = (
            multi_df.groupby("query")["click_share"]
            .max()
            .reset_index()
            .rename(columns={"click_share": "max_page_click_share"})
        )

        # Consolidation opportunity: no page dominates (max share < 50%)
        # Also include zero-click queries (all pages have 0 clicks) as opportunities
        consolidation_queries = max_share_per_query[
            max_share_per_query["max_page_click_share"] < 50
        ]
        opportunity_count = len(consolidation_queries)
        opportunity_rate = (
            opportunity_count / total_multi_page * 100
        ) if total_multi_page > 0 else 0.0

        # Severity
        if opportunity_rate > 50:
            severity = Severity.HIGH
        elif opportunity_rate > 35:
            severity = Severity.MEDIUM
        elif opportunity_rate > 20:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{opportunity_count:,} of {total_multi_page:,} multi-page queries "
            f"({opportunity_rate:.1f}%) lack a dominant page (no single page captures "
            f">50% of clicks). These represent content consolidation opportunities — "
            f"merging competing pages could strengthen ranking authority."
            if opportunity_rate > 20
            else f"{opportunity_count:,} of {total_multi_page:,} multi-page queries "
            f"({opportunity_rate:.1f}%) lack a dominant page. "
            f"Content targeting is generally well-focused with clear page assignments."
        )

        # Build data table: show consolidation opportunity queries
        opportunity_query_set = set(consolidation_queries["query"])
        opportunity_detail = (
            multi_df[multi_df["query"].isin(opportunity_query_set)]
            .sort_values(["query", "clicks"], ascending=[True, False])
        )

        # Create a summary view: one row per query showing page count and top click share
        query_summary = (
            opportunity_detail.groupby("query")
            .agg(
                pages=("page", "nunique"),
                total_clicks=("clicks", "sum"),
                total_impressions=("impressions", "sum"),
                max_click_share=("click_share", "max"),
            )
            .reset_index()
            .sort_values("total_impressions", ascending=False)
            .head(25)
        )
        query_summary["max_click_share"] = query_summary["max_click_share"].round(1)
        display_df = query_summary

        recommendations = []
        if opportunity_rate > 35:
            recommendations.extend([
                "Identify the strongest page for each consolidation query and merge weaker pages into it via 301 redirects.",
                "Review page intent — competing pages may target different aspects of the same query; consider differentiating them.",
                "Consolidate similar content into comprehensive pillar pages that serve the query thoroughly.",
                "Strengthen the chosen canonical page with internal links from other pages on the site.",
                "After consolidation, update the sitemap and monitor for ranking improvements.",
            ])
        elif opportunity_rate > 20:
            recommendations.extend([
                "Prioritize high-impression consolidation queries where merging pages would have the greatest impact.",
                "Use internal linking signals to clarify which page should be primary for each contested query.",
                "Consider whether multiple pages intentionally target different intents before consolidating.",
            ])
        else:
            recommendations.append(
                "Content consolidation opportunities are minimal. Monitor for emerging overlap as new content is published."
            )

        return self.create_result(
            metric_id=99,
            severity=severity,
            summary=summary,
            computed_value=round(opportunity_rate, 2),
            affected_count=opportunity_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "multi_page_queries": total_multi_page,
                "consolidation_opportunities": opportunity_count,
                "opportunity_rate_pct": round(opportunity_rate, 2),
                "total_queries": len(query_page_counts),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 100 — Top-10% URL Traffic Concentration
    # ------------------------------------------------------------------ #
    def metric_top_10_pct_url_traffic_concentration(self) -> MetricResult:
        """Percentage of total clicks captured by the top 10% of URLs."""
        df = self.get_df("page_90d")
        if df.empty:
            return self._error_result(100, "No page data available")

        total_urls = len(df)
        if total_urls == 0:
            return self._error_result(100, "No URLs found in page data")

        total_clicks = df["clicks"].sum()
        if total_clicks == 0:
            return self.create_result(
                metric_id=100,
                severity=Severity.INSIGHT,
                summary=(
                    f"No clicks recorded across {total_urls:,} URLs. "
                    f"Traffic concentration cannot be calculated."
                ),
                computed_value=0.0,
                affected_count=0,
                recommendations=[
                    "Investigate why no URLs are generating clicks — check indexation and ranking status."
                ],
                details={
                    "total_urls": total_urls,
                    "total_clicks": 0,
                },
            )

        # Sort by clicks descending
        sorted_df = df.sort_values("clicks", ascending=False).reset_index(drop=True)

        # Top 10% of URLs (at least 1)
        top_10_pct_count = max(1, int(np.ceil(total_urls * 0.10)))
        top_10_pct_df = sorted_df.head(top_10_pct_count)
        top_10_pct_clicks = top_10_pct_df["clicks"].sum()
        concentration = (top_10_pct_clicks / total_clicks * 100) if total_clicks > 0 else 0.0

        # Also compute the bottom 90% stats
        bottom_90_pct_count = total_urls - top_10_pct_count
        bottom_90_pct_clicks = total_clicks - top_10_pct_clicks
        bottom_90_pct_avg_clicks = (
            bottom_90_pct_clicks / bottom_90_pct_count
        ) if bottom_90_pct_count > 0 else 0.0

        # Severity
        if concentration > 90:
            severity = Severity.HIGH
        elif concentration > 80:
            severity = Severity.MEDIUM
        elif concentration > 70:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"The top {top_10_pct_count:,} URLs (10% of {total_urls:,}) capture "
            f"{concentration:.1f}% of all clicks ({int(top_10_pct_clicks):,} of {int(total_clicks):,}). "
            f"{'High concentration indicates over-reliance on a small number of pages — if these lose rankings, traffic could drop significantly.' if concentration > 80 else 'Traffic is reasonably distributed across the content library.'}"
        )

        # Build data table: show top 10% URLs
        display_df = (
            top_10_pct_df
            [["page", "clicks", "impressions", "ctr", "position"]]
            .head(25)
            .copy()
        )
        display_df["click_share_pct"] = (
            display_df["clicks"] / total_clicks * 100
        ).round(2)

        recommendations = []
        if concentration > 80:
            recommendations.extend([
                "Diversify traffic sources by investing in content that targets a broader range of queries and topics.",
                "Strengthen the ranking stability of top pages through robust backlink profiles and content freshness.",
                "Identify high-potential underperforming pages and optimize them to earn a larger share of clicks.",
                "Build content clusters around top-performing pages to create supporting traffic sources.",
                "Monitor top-traffic pages closely for ranking volatility — a single page dropping could cause major traffic loss.",
            ])
        elif concentration > 70:
            recommendations.extend([
                "Continue growing mid-tier pages to reduce dependence on top performers.",
                "Audit underperforming pages to identify quick wins that could redistribute traffic more evenly.",
                "Ensure top-performing pages have strong internal linking support and are technically optimized.",
            ])
        else:
            recommendations.append(
                "Traffic distribution is well-balanced across the content library. Maintain this diversification."
            )

        return self.create_result(
            metric_id=100,
            severity=severity,
            summary=summary,
            computed_value=round(concentration, 2),
            affected_count=top_10_pct_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "top_10_pct_url_count": top_10_pct_count,
                "total_urls": total_urls,
                "top_10_pct_clicks": int(top_10_pct_clicks),
                "total_clicks": int(total_clicks),
                "concentration_pct": round(concentration, 2),
                "bottom_90_pct_avg_clicks": round(bottom_90_pct_avg_clicks, 2),
            },
        )
