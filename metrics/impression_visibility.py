"""Impression & Visibility metrics (22-27).

Measures how a site's impressions are growing, where they come from
(SERP features, featured snippets), how they distribute across topic
clusters, and the depth of query visibility per URL.
"""

import logging
from typing import Optional
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from metrics.base_metric import BaseMetricGroup
from models.metric_result import MetricResult, Severity, TrendDirection

logger = logging.getLogger(__name__)


class ImpressionVisibilityMetrics(BaseMetricGroup):
    """Metrics 22-27: Impression & Visibility."""

    METRIC_REGISTRY: dict[int, str] = {
        22: "impression_growth_rate_mom",
        23: "impression_growth_rate_yoy",
        24: "serp_feature_impression_share",
        25: "featured_snippet_impression_rate",
        26: "share_of_voice_by_topic_cluster",
        27: "query_impression_depth",
    }

    # ------------------------------------------------------------------ #
    # 22 — Impression Growth Rate (MoM)
    # ------------------------------------------------------------------ #
    def impression_growth_rate_mom(self) -> MetricResult:
        """Percent change in impressions per URL, current 30d vs previous 30d."""
        df_90d = self.get_df("page_date_90d")
        df_30d = self.get_df("page_date_30d")

        if df_90d.empty or df_30d.empty:
            return self.create_result(
                metric_id=22,
                severity=Severity.INSIGHT,
                summary="Insufficient data to calculate MoM impression growth.",
                recommendations=["Ensure at least 60 days of GSC data is available."],
            )

        # Determine date boundary: the earliest date in the 30d set marks
        # the split point.  Everything in 90d that is *before* this date
        # and within 30 days before it forms the previous period.
        df_90d = df_90d.copy()
        df_30d = df_30d.copy()
        df_90d["date"] = pd.to_datetime(df_90d["date"])
        df_30d["date"] = pd.to_datetime(df_30d["date"])

        current_start = df_30d["date"].min()
        previous_start = current_start - pd.Timedelta(days=30)

        current = df_30d.groupby("page", as_index=False)["impressions"].sum()
        current.rename(columns={"impressions": "current_impressions"}, inplace=True)

        prev = df_90d[
            (df_90d["date"] >= previous_start) & (df_90d["date"] < current_start)
        ]
        prev = prev.groupby("page", as_index=False)["impressions"].sum()
        prev.rename(columns={"impressions": "previous_impressions"}, inplace=True)

        merged = current.merge(prev, on="page", how="outer").fillna(0)

        # Avoid division by zero — treat 0 previous as NaN growth
        merged["growth_pct"] = np.where(
            merged["previous_impressions"] > 0,
            (
                (merged["current_impressions"] - merged["previous_impressions"])
                / merged["previous_impressions"]
            )
            * 100,
            np.nan,
        )

        valid = merged.dropna(subset=["growth_pct"])

        if valid.empty:
            return self.create_result(
                metric_id=22,
                severity=Severity.INSIGHT,
                summary="No URLs with comparable impression data across both months.",
                recommendations=["Wait for more data to accumulate."],
            )

        site_avg_growth = valid["growth_pct"].mean()

        # Declining URLs (negative growth)
        declining = valid[valid["growth_pct"] < -10].sort_values("growth_pct")
        growing = valid[valid["growth_pct"] > 10].sort_values(
            "growth_pct", ascending=False
        )

        # Severity based on site-wide average
        if site_avg_growth <= -20:
            severity = Severity.CRITICAL
            trend = TrendDirection.DECLINING
        elif site_avg_growth <= -10:
            severity = Severity.HIGH
            trend = TrendDirection.DECLINING
        elif site_avg_growth < 0:
            severity = Severity.MEDIUM
            trend = TrendDirection.DECLINING
        elif site_avg_growth < 5:
            severity = Severity.LOW
            trend = TrendDirection.STABLE
        else:
            severity = Severity.INSIGHT
            trend = TrendDirection.IMPROVING

        # Data table: top declining + top growing
        table = pd.concat([declining.head(15), growing.head(10)]).copy()
        table["growth_pct"] = table["growth_pct"].round(1)
        table = table[
            ["page", "previous_impressions", "current_impressions", "growth_pct"]
        ].rename(
            columns={
                "page": "URL",
                "previous_impressions": "Prev 30d Impr",
                "current_impressions": "Curr 30d Impr",
                "growth_pct": "Growth %",
            }
        )

        recommendations = []
        if len(declining) > 0:
            recommendations.append(
                f"{len(declining)} URLs lost >10% impressions MoM. "
                "Investigate whether content is stale, rankings dropped, or "
                "search demand shifted."
            )
        if len(growing) > 0:
            recommendations.append(
                f"{len(growing)} URLs gained >10% impressions MoM. "
                "Double down on these with internal linking and content updates."
            )
        if site_avg_growth < -5:
            recommendations.append(
                "Site-wide impression decline detected. Check for algorithm "
                "updates, technical issues, or seasonal demand drops."
            )

        return self.create_result(
            metric_id=22,
            severity=severity,
            summary=(
                f"Site-wide MoM impression growth is {site_avg_growth:+.1f}%. "
                f"{len(declining)} URLs declining (>10%), "
                f"{len(growing)} URLs growing (>10%)."
            ),
            computed_value=round(site_avg_growth, 2),
            affected_count=len(declining),
            data_table=table,
            recommendations=recommendations,
            trend_direction=trend,
            benchmark_comparison=(
                "above" if site_avg_growth > 5 else
                "below" if site_avg_growth < -5 else "at"
            ),
        )

    # ------------------------------------------------------------------ #
    # 23 — Impression Growth Rate (YoY)
    # ------------------------------------------------------------------ #
    def impression_growth_rate_yoy(self) -> MetricResult:
        """Percent change in impressions per URL, current 90d vs same 90d last year."""
        df_90d = self.get_df("page_date_90d")
        df_365d = self.get_df("page_date_365d")

        if df_90d.empty or df_365d.empty:
            return self.create_result(
                metric_id=23,
                severity=Severity.INSIGHT,
                summary="Insufficient data to calculate YoY impression growth.",
                recommendations=[
                    "Ensure 365 days of GSC data is available for YoY analysis."
                ],
            )

        df_90d = df_90d.copy()
        df_365d = df_365d.copy()
        df_90d["date"] = pd.to_datetime(df_90d["date"])
        df_365d["date"] = pd.to_datetime(df_365d["date"])

        # Current period: the 90d window
        current_start = df_90d["date"].min()
        current_end = df_90d["date"].max()
        period_days = (current_end - current_start).days + 1

        # Previous year: same calendar window shifted back 365 days
        prev_start = current_start - pd.Timedelta(days=365)
        prev_end = current_end - pd.Timedelta(days=365)

        current = df_90d.groupby("page", as_index=False)["impressions"].sum()
        current.rename(columns={"impressions": "current_impressions"}, inplace=True)

        prev = df_365d[
            (df_365d["date"] >= prev_start) & (df_365d["date"] <= prev_end)
        ]
        prev = prev.groupby("page", as_index=False)["impressions"].sum()
        prev.rename(columns={"impressions": "previous_impressions"}, inplace=True)

        merged = current.merge(prev, on="page", how="outer").fillna(0)

        merged["growth_pct"] = np.where(
            merged["previous_impressions"] > 0,
            (
                (merged["current_impressions"] - merged["previous_impressions"])
                / merged["previous_impressions"]
            )
            * 100,
            np.nan,
        )

        valid = merged.dropna(subset=["growth_pct"])

        if valid.empty:
            return self.create_result(
                metric_id=23,
                severity=Severity.INSIGHT,
                summary="No URLs with comparable impression data across both years.",
                recommendations=["Ensure GSC property has over 1 year of history."],
            )

        site_avg_growth = valid["growth_pct"].mean()

        declining = valid[valid["growth_pct"] < -20].sort_values("growth_pct")
        growing = valid[valid["growth_pct"] > 20].sort_values(
            "growth_pct", ascending=False
        )

        if site_avg_growth <= -30:
            severity = Severity.CRITICAL
            trend = TrendDirection.DECLINING
        elif site_avg_growth <= -15:
            severity = Severity.HIGH
            trend = TrendDirection.DECLINING
        elif site_avg_growth < 0:
            severity = Severity.MEDIUM
            trend = TrendDirection.DECLINING
        elif site_avg_growth < 10:
            severity = Severity.LOW
            trend = TrendDirection.STABLE
        else:
            severity = Severity.INSIGHT
            trend = TrendDirection.IMPROVING

        table = pd.concat([declining.head(15), growing.head(10)]).copy()
        table["growth_pct"] = table["growth_pct"].round(1)
        table = table[
            ["page", "previous_impressions", "current_impressions", "growth_pct"]
        ].rename(
            columns={
                "page": "URL",
                "previous_impressions": "Last Year Impr",
                "current_impressions": "Current Impr",
                "growth_pct": "YoY Growth %",
            }
        )

        recommendations = []
        if len(declining) > 0:
            recommendations.append(
                f"{len(declining)} URLs lost >20% impressions YoY. "
                "Audit for content freshness, lost backlinks, or competitive displacement."
            )
        if len(growing) > 0:
            recommendations.append(
                f"{len(growing)} URLs gained >20% impressions YoY. "
                "Analyze what is driving growth and replicate across similar content."
            )
        if site_avg_growth < -10:
            recommendations.append(
                "Significant year-over-year visibility loss. Review Google algorithm "
                "update timelines and compare with ranking changes."
            )

        return self.create_result(
            metric_id=23,
            severity=severity,
            summary=(
                f"Site-wide YoY impression growth is {site_avg_growth:+.1f}% "
                f"(comparing {period_days}-day windows). "
                f"{len(declining)} URLs declining (>20%), "
                f"{len(growing)} URLs growing (>20%)."
            ),
            computed_value=round(site_avg_growth, 2),
            affected_count=len(declining),
            data_table=table,
            recommendations=recommendations,
            trend_direction=trend,
            benchmark_comparison=(
                "above" if site_avg_growth > 10 else
                "below" if site_avg_growth < -10 else "at"
            ),
        )

    # ------------------------------------------------------------------ #
    # 24 — SERP Feature Impression Share
    # ------------------------------------------------------------------ #
    def serp_feature_impression_share(self) -> MetricResult:
        """Percent of total impressions coming from SERP features / rich results."""
        df_sa = self.get_df("search_appearance_90d")
        df_sa_page = self.get_df("search_appearance_page_90d")
        df_page = self.get_df("page_90d")

        if df_sa.empty:
            return self.create_result(
                metric_id=24,
                severity=Severity.INSIGHT,
                summary="No search appearance data available.",
                recommendations=[
                    "Ensure GSC has searchAppearance data. This requires "
                    "structured data or rich result eligibility."
                ],
            )

        # Total web impressions across all pages
        total_web_impressions = (
            df_page["impressions"].sum() if not df_page.empty else 0
        )

        if total_web_impressions == 0:
            return self.create_result(
                metric_id=24,
                severity=Severity.INSIGHT,
                summary="Zero total web impressions — cannot calculate SERP feature share.",
                recommendations=["Check that GSC data was fetched correctly."],
            )

        # Sum impressions by search appearance type
        sa_summary = (
            df_sa.groupby("searchAppearance", as_index=False)["impressions"]
            .sum()
            .sort_values("impressions", ascending=False)
        )

        total_feature_impressions = sa_summary["impressions"].sum()
        feature_share = (total_feature_impressions / total_web_impressions) * 100

        # Per-page breakdown if available
        page_table = pd.DataFrame()
        if not df_sa_page.empty:
            page_agg = (
                df_sa_page.groupby(["page", "searchAppearance"], as_index=False)[
                    "impressions"
                ]
                .sum()
                .sort_values("impressions", ascending=False)
            )
            page_table = page_agg.head(25).rename(
                columns={
                    "page": "URL",
                    "searchAppearance": "Feature Type",
                    "impressions": "Feature Impressions",
                }
            )

        # Severity — low feature presence = opportunity
        if feature_share < 2:
            severity = Severity.HIGH
        elif feature_share < 5:
            severity = Severity.MEDIUM
        elif feature_share < 15:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        # Build feature type summary
        feature_list = ", ".join(
            f"{row['searchAppearance']} ({row['impressions']:,.0f})"
            for _, row in sa_summary.head(5).iterrows()
        )

        recommendations = []
        if feature_share < 5:
            recommendations.append(
                "SERP feature presence is low. Implement structured data "
                "(FAQ, HowTo, Product, Review) to qualify for rich results."
            )
        recommendations.append(
            "Audit top-performing pages for structured data gaps. "
            "Pages with high impressions but no SERP features have the "
            "greatest uplift potential."
        )
        if "RICH_RESULT" not in df_sa.get("searchAppearance", pd.Series()).values:
            recommendations.append(
                "No rich result appearances detected. Add Schema.org markup "
                "to eligible content types."
            )

        # Use the feature breakdown as the main table, page breakdown as secondary
        summary_table = sa_summary.copy()
        summary_table["share_pct"] = (
            summary_table["impressions"] / total_web_impressions * 100
        ).round(2)
        summary_table = summary_table.rename(
            columns={
                "searchAppearance": "Feature Type",
                "impressions": "Impressions",
                "share_pct": "Share %",
            }
        )

        # Combine: feature summary on top, then page detail
        display_table = summary_table if page_table.empty else page_table

        return self.create_result(
            metric_id=24,
            severity=severity,
            summary=(
                f"SERP features account for {feature_share:.1f}% of total impressions "
                f"({total_feature_impressions:,.0f} / {total_web_impressions:,.0f}). "
                f"Top features: {feature_list}."
            ),
            computed_value=round(feature_share, 2),
            affected_count=len(sa_summary),
            data_table=display_table,
            recommendations=recommendations,
            details={
                "feature_breakdown": summary_table.to_dict(orient="records"),
            },
        )

    # ------------------------------------------------------------------ #
    # 25 — Featured Snippet Impression Rate
    # ------------------------------------------------------------------ #
    def featured_snippet_impression_rate(self) -> MetricResult:
        """Percent of impressions specifically from featured snippets."""
        df_sa = self.get_df("search_appearance_90d")
        df_sa_page = self.get_df("search_appearance_page_90d")
        df_page = self.get_df("page_90d")

        if df_sa.empty:
            return self.create_result(
                metric_id=25,
                severity=Severity.INSIGHT,
                summary="No search appearance data available for snippet analysis.",
                recommendations=[
                    "Implement structured data and optimise content for "
                    "featured snippets (definitions, lists, tables)."
                ],
            )

        total_web_impressions = (
            df_page["impressions"].sum() if not df_page.empty else 0
        )

        if total_web_impressions == 0:
            return self.create_result(
                metric_id=25,
                severity=Severity.INSIGHT,
                summary="Zero total web impressions — cannot calculate snippet rate.",
                recommendations=["Check that GSC data was fetched correctly."],
            )

        # GSC searchAppearance values related to featured snippets
        snippet_keywords = [
            "FEATURED_SNIPPET",
            "RICHsnippet",
            "featured_snippet",
            "richSnippet",
        ]

        snippet_rows = df_sa[
            df_sa["searchAppearance"].str.lower().str.contains(
                "|".join(k.lower() for k in snippet_keywords), na=False
            )
        ]

        snippet_impressions = snippet_rows["impressions"].sum() if not snippet_rows.empty else 0
        snippet_rate = (snippet_impressions / total_web_impressions) * 100

        # Per-page snippet data
        page_table = pd.DataFrame()
        if not df_sa_page.empty:
            snippet_pages = df_sa_page[
                df_sa_page["searchAppearance"].str.lower().str.contains(
                    "|".join(k.lower() for k in snippet_keywords), na=False
                )
            ]
            if not snippet_pages.empty:
                page_table = (
                    snippet_pages.groupby("page", as_index=False)["impressions"]
                    .sum()
                    .sort_values("impressions", ascending=False)
                    .head(25)
                    .rename(
                        columns={
                            "page": "URL",
                            "impressions": "Snippet Impressions",
                        }
                    )
                )

        # Severity — no snippets is an opportunity, not necessarily a problem
        if snippet_rate == 0:
            severity = Severity.MEDIUM
        elif snippet_rate < 1:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        recommendations = []
        if snippet_rate == 0:
            recommendations.append(
                "No featured snippet impressions detected. Target snippet-friendly "
                "queries with concise answer paragraphs (40-60 words), numbered lists, "
                "and comparison tables."
            )
        elif snippet_rate < 1:
            recommendations.append(
                "Snippet presence is minimal. Identify high-impression queries "
                "where competitors hold the snippet and create better-structured "
                "answers."
            )
        else:
            recommendations.append(
                "Featured snippets are contributing impressions. Protect these "
                "positions by keeping content up to date and monitoring for "
                "snippet theft by competitors."
            )
        recommendations.append(
            "Focus snippet optimization on informational queries with "
            "question-format patterns (how, what, why, when)."
        )

        return self.create_result(
            metric_id=25,
            severity=severity,
            summary=(
                f"Featured snippets account for {snippet_rate:.2f}% of total "
                f"impressions ({snippet_impressions:,.0f} snippet impressions "
                f"out of {total_web_impressions:,.0f} total)."
            ),
            computed_value=round(snippet_rate, 4),
            affected_count=len(page_table) if not page_table.empty else 0,
            data_table=page_table if not page_table.empty else None,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------ #
    # 26 — Share of Voice by Topic Cluster
    # ------------------------------------------------------------------ #
    def share_of_voice_by_topic_cluster(self) -> MetricResult:
        """Each URL's impression share within its topic cluster."""
        df_qp = self.get_df("query_page_90d")

        if df_qp.empty:
            return self.create_result(
                metric_id=26,
                severity=Severity.INSIGHT,
                summary="No query-page data available for topic cluster analysis.",
                recommendations=[
                    "Ensure query-page 90d data is fetched before running this metric."
                ],
            )

        df_qp = df_qp.copy()

        # Assign topic cluster to each query — AI classification first,
        # then fall back to URL directory grouping.
        df_qp["topic_cluster"] = df_qp["query"].apply(self.get_topic_cluster)

        has_ai_clusters = df_qp["topic_cluster"].notna().any()

        if not has_ai_clusters:
            # Fallback: use the first meaningful path segment of the URL
            df_qp["topic_cluster"] = df_qp["page"].apply(
                self._extract_url_directory
            )

        # Drop rows with no cluster assignment
        df_qp = df_qp[df_qp["topic_cluster"].notna() & (df_qp["topic_cluster"] != "")]

        if df_qp.empty:
            return self.create_result(
                metric_id=26,
                severity=Severity.INSIGHT,
                summary="Could not assign topic clusters to any queries.",
                recommendations=[
                    "Enable AI classification for better topic clustering, "
                    "or ensure URLs have a clear directory structure."
                ],
            )

        # Total impressions per cluster
        cluster_totals = (
            df_qp.groupby("topic_cluster", as_index=False)["impressions"]
            .sum()
            .rename(columns={"impressions": "cluster_impressions"})
        )

        # Per-page impressions within each cluster
        page_cluster = (
            df_qp.groupby(["topic_cluster", "page"], as_index=False)["impressions"]
            .sum()
        )

        page_cluster = page_cluster.merge(cluster_totals, on="topic_cluster")
        page_cluster["share_pct"] = (
            page_cluster["impressions"] / page_cluster["cluster_impressions"] * 100
        ).round(2)

        # Identify clusters where impression share is highly concentrated
        # (one page dominates) vs. fragmented
        cluster_stats = (
            page_cluster.groupby("topic_cluster")
            .agg(
                page_count=("page", "nunique"),
                max_share=("share_pct", "max"),
                total_impressions=("cluster_impressions", "first"),
            )
            .reset_index()
            .sort_values("total_impressions", ascending=False)
        )

        fragmented_clusters = cluster_stats[
            (cluster_stats["page_count"] >= 3) & (cluster_stats["max_share"] < 40)
        ]

        total_clusters = len(cluster_stats)
        fragmented_count = len(fragmented_clusters)

        if fragmented_count / max(total_clusters, 1) > 0.5:
            severity = Severity.MEDIUM
        elif fragmented_count > 3:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        # Build display table: top clusters with their top page
        top_entries = (
            page_cluster.sort_values(
                ["cluster_impressions", "share_pct"], ascending=[False, False]
            )
            .groupby("topic_cluster")
            .head(3)
            .head(25)
        )

        display_table = top_entries[
            ["topic_cluster", "page", "impressions", "share_pct"]
        ].rename(
            columns={
                "topic_cluster": "Topic Cluster",
                "page": "URL",
                "impressions": "Impressions",
                "share_pct": "Share %",
            }
        )

        cluster_method = "AI classification" if has_ai_clusters else "URL directory grouping"

        recommendations = []
        if fragmented_count > 0:
            recommendations.append(
                f"{fragmented_count} topic clusters have fragmented visibility "
                "(no single page captures >40% share). Consider consolidating "
                "content or building a clear pillar page for each cluster."
            )
        recommendations.append(
            "For each cluster, designate a primary pillar page and link "
            "supporting content to it to concentrate topical authority."
        )
        if not has_ai_clusters:
            recommendations.append(
                "Topic clusters were inferred from URL directories. "
                "Enable AI classification for more accurate semantic clustering."
            )

        return self.create_result(
            metric_id=26,
            severity=severity,
            summary=(
                f"Identified {total_clusters} topic clusters ({cluster_method}). "
                f"{fragmented_count} clusters have fragmented impression share "
                f"across 3+ pages."
            ),
            computed_value=round(
                fragmented_count / max(total_clusters, 1) * 100, 2
            ),
            affected_count=fragmented_count,
            data_table=display_table,
            recommendations=recommendations,
            details={
                "cluster_method": cluster_method,
                "total_clusters": total_clusters,
                "fragmented_clusters": fragmented_count,
            },
        )

    @staticmethod
    def _extract_url_directory(url: str) -> str:
        """Extract the first meaningful path directory from a URL.

        Examples:
            https://example.com/blog/my-post -> blog
            https://example.com/products/shoes/red -> products
            https://example.com/ -> (root)
        """
        try:
            path = urlparse(url).path.strip("/")
            if not path:
                return "(root)"
            segments = path.split("/")
            return segments[0] if segments else "(root)"
        except Exception:
            return "(unknown)"

    # ------------------------------------------------------------------ #
    # 27 — Query Impression Depth
    # ------------------------------------------------------------------ #
    def query_impression_depth(self) -> MetricResult:
        """Average impressions per query for each URL.

        High depth = concentrated visibility on fewer queries.
        Low depth = broad spread across many queries with low impressions each.
        """
        df_qp = self.get_df("query_page_90d")

        if df_qp.empty:
            return self.create_result(
                metric_id=27,
                severity=Severity.INSIGHT,
                summary="No query-page data available for impression depth analysis.",
                recommendations=[
                    "Ensure query-page 90d data is fetched for this metric."
                ],
            )

        # Group by page: total impressions and unique query count
        page_stats = (
            df_qp.groupby("page")
            .agg(
                total_impressions=("impressions", "sum"),
                unique_queries=("query", "nunique"),
            )
            .reset_index()
        )

        page_stats["avg_impr_per_query"] = (
            page_stats["total_impressions"] / page_stats["unique_queries"]
        ).round(2)

        # Site-wide median depth
        site_median_depth = page_stats["avg_impr_per_query"].median()

        # Flag extremes
        # Very high depth: a few queries dominate (risk of dependency)
        high_depth_threshold = site_median_depth * 3 if site_median_depth > 0 else 100
        low_depth_threshold = max(site_median_depth * 0.3, 2)

        concentrated = page_stats[
            page_stats["avg_impr_per_query"] > high_depth_threshold
        ].sort_values("avg_impr_per_query", ascending=False)

        thin_spread = page_stats[
            (page_stats["avg_impr_per_query"] < low_depth_threshold)
            & (page_stats["unique_queries"] >= 3)
        ].sort_values("avg_impr_per_query")

        # Severity: too many concentrated pages = risky dependency
        concentrated_pct = len(concentrated) / max(len(page_stats), 1) * 100
        if concentrated_pct > 30:
            severity = Severity.MEDIUM
        elif concentrated_pct > 15:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        # Build table: concentrated pages first, then thin-spread
        table_concentrated = concentrated.head(15).copy()
        table_concentrated["depth_label"] = "High (concentrated)"
        table_thin = thin_spread.head(10).copy()
        table_thin["depth_label"] = "Low (thin spread)"

        display_table = pd.concat([table_concentrated, table_thin])
        display_table = display_table[
            ["page", "total_impressions", "unique_queries", "avg_impr_per_query", "depth_label"]
        ].rename(
            columns={
                "page": "URL",
                "total_impressions": "Total Impressions",
                "unique_queries": "Unique Queries",
                "avg_impr_per_query": "Avg Impr/Query",
                "depth_label": "Depth Type",
            }
        )

        recommendations = []
        if len(concentrated) > 0:
            recommendations.append(
                f"{len(concentrated)} URLs depend heavily on a small number of "
                "high-impression queries. Diversify their keyword targeting "
                "to reduce dependency risk."
            )
        if len(thin_spread) > 0:
            recommendations.append(
                f"{len(thin_spread)} URLs have very low impressions per query "
                "(thin spread). These may rank for many irrelevant queries — "
                "tighten content focus and improve topical relevance."
            )
        recommendations.append(
            f"Site median impression depth is {site_median_depth:.1f} "
            "impressions per query. A healthy range depends on the niche, "
            "but aim for a balance between depth and breadth."
        )

        return self.create_result(
            metric_id=27,
            severity=severity,
            summary=(
                f"Median impression depth is {site_median_depth:.1f} impressions/query. "
                f"{len(concentrated)} URLs have highly concentrated visibility, "
                f"{len(thin_spread)} URLs have thin spread across queries."
            ),
            computed_value=round(site_median_depth, 2),
            affected_count=len(concentrated) + len(thin_spread),
            data_table=display_table if not display_table.empty else None,
            recommendations=recommendations,
        )
