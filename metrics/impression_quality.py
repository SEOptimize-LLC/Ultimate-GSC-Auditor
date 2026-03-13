"""Impression Quality metrics (69-77).

Analyzes the quality and distribution of impressions across position
ranges, search types (web, image, video, discover, news), rich results,
and impression-to-click funnel efficiency.
"""

import logging
from datetime import timedelta

import pandas as pd

from metrics.base_metric import BaseMetricGroup
from models.metric_result import MetricResult, Severity, TrendDirection

logger = logging.getLogger(__name__)


class ImpressionQualityMetrics(BaseMetricGroup):
    """Metrics 69-77: Impression Quality analysis."""

    METRIC_REGISTRY: dict[int, str] = {
        69: "metric_page_1_impression_share",
        70: "metric_page_2_impression_share",
        71: "metric_deep_page_impression_rate",
        72: "metric_impression_to_click_funnel_loss_rate",
        73: "metric_new_vs_returning_query_impression_split",
        74: "metric_rich_result_impression_rate",
        75: "metric_video_result_impression_share",
        76: "metric_image_result_impression_share",
        77: "metric_news_discover_impression_share",
    }

    # ------------------------------------------------------------------ #
    # Metric 69 — Page 1 Impression Share
    # ------------------------------------------------------------------ #
    def metric_page_1_impression_share(self) -> MetricResult:
        """Impressions from queries with avg position <= 10 as share of total."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(69, "No query data available")

        total_impressions = df["impressions"].sum()
        if total_impressions == 0:
            return self._error_result(69, "No impressions recorded in data")

        page_1 = df[df["position"] <= 10.0]
        page_1_impressions = page_1["impressions"].sum()
        page_1_share = (page_1_impressions / total_impressions * 100)

        page_1_queries = len(page_1)
        total_queries = len(df)
        page_1_clicks = page_1["clicks"].sum()
        total_clicks = df["clicks"].sum()
        page_1_click_share = (
            (page_1_clicks / total_clicks * 100) if total_clicks > 0 else 0.0
        )

        if page_1_share < 30:
            severity = Severity.HIGH
        elif page_1_share < 50:
            severity = Severity.MEDIUM
        elif page_1_share < 70:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"Page 1 impressions account for {page_1_share:.1f}% of total impressions "
            f"({page_1_impressions:,} of {total_impressions:,}). "
            f"{page_1_queries:,} of {total_queries:,} queries rank on page 1, "
            f"capturing {page_1_click_share:.1f}% of all clicks. "
            f"{'Low page 1 impression share means most visibility comes from lower-value positions.' if page_1_share < 50 else 'Majority of impressions come from high-value page 1 positions.'}"
        )

        display_df = (
            page_1
            .sort_values("impressions", ascending=False)
            [["query", "impressions", "clicks", "position", "ctr"]]
            .head(25)
        )

        recommendations = []
        if page_1_share < 50:
            recommendations.extend([
                "Focus on moving page 2 and page 3 queries to page 1 through content optimization and link building.",
                "Prioritize queries with the highest impressions that are just outside page 1 (positions 11-15).",
                "Audit title tags and meta descriptions to improve CTR once queries reach page 1.",
                "Build topical authority through content clustering to lift related queries into page 1.",
            ])
        else:
            recommendations.append(
                "Page 1 impression share is strong. Focus on improving positions within page 1 (moving from 4-10 to top 3) for even greater click share."
            )

        return self.create_result(
            metric_id=69,
            severity=severity,
            summary=summary,
            computed_value=round(page_1_share, 2),
            affected_count=page_1_queries,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            benchmark_comparison="above" if page_1_share >= 50 else "below",
            details={
                "page_1_impressions": int(page_1_impressions),
                "total_impressions": int(total_impressions),
                "page_1_queries": page_1_queries,
                "total_queries": total_queries,
                "page_1_click_share": round(page_1_click_share, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 70 — Page 2 Impression Share
    # ------------------------------------------------------------------ #
    def metric_page_2_impression_share(self) -> MetricResult:
        """Impressions from queries with avg position 11-20 as share of total."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(70, "No query data available")

        total_impressions = df["impressions"].sum()
        if total_impressions == 0:
            return self._error_result(70, "No impressions recorded in data")

        page_2 = df[(df["position"] > 10.0) & (df["position"] <= 20.0)]
        page_2_impressions = page_2["impressions"].sum()
        page_2_share = (page_2_impressions / total_impressions * 100)

        page_2_queries = len(page_2)
        total_queries = len(df)
        page_2_clicks = page_2["clicks"].sum()
        page_2_ctr = (
            (page_2_clicks / page_2_impressions * 100)
            if page_2_impressions > 0 else 0.0
        )

        severity = Severity.INSIGHT

        summary = (
            f"Page 2 impressions (positions 11-20) account for {page_2_share:.1f}% "
            f"of total impressions ({page_2_impressions:,} of {total_impressions:,}). "
            f"{page_2_queries:,} queries sit on page 2 with an average CTR of "
            f"{page_2_ctr:.2f}%. These represent the strongest quick-win opportunities "
            f"since moving them to page 1 could dramatically increase clicks."
        )

        display_df = (
            page_2
            .sort_values("impressions", ascending=False)
            [["query", "impressions", "clicks", "position", "ctr"]]
            .head(25)
        )

        recommendations = [
            "Page 2 queries are the highest-ROI optimization targets — small ranking improvements yield disproportionate click gains.",
            "Audit the top page 2 queries by impression count and prioritize content enhancements for those topics.",
            "Add internal links from authoritative pages to the URLs ranking for these page 2 queries.",
            "Consider updating content freshness, adding structured data, and building targeted backlinks to push into page 1.",
        ]

        return self.create_result(
            metric_id=70,
            severity=severity,
            summary=summary,
            computed_value=round(page_2_share, 2),
            affected_count=page_2_queries,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            opportunity_value=f"{page_2_queries:,} queries could be moved to page 1",
            details={
                "page_2_impressions": int(page_2_impressions),
                "total_impressions": int(total_impressions),
                "page_2_queries": page_2_queries,
                "page_2_avg_ctr": round(page_2_ctr, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 71 — Deep-Page Impression Rate
    # ------------------------------------------------------------------ #
    def metric_deep_page_impression_rate(self) -> MetricResult:
        """Impressions from queries with avg position 51+ as share of total."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(71, "No query data available")

        total_impressions = df["impressions"].sum()
        if total_impressions == 0:
            return self._error_result(71, "No impressions recorded in data")

        deep = df[df["position"] > 50.0]
        deep_impressions = deep["impressions"].sum()
        deep_share = (deep_impressions / total_impressions * 100)

        deep_queries = len(deep)
        total_queries = len(df)
        deep_clicks = deep["clicks"].sum()

        if deep_share > 20:
            severity = Severity.MEDIUM
        elif deep_share > 10:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        summary = (
            f"Deep-page impressions (position 51+) account for {deep_share:.1f}% "
            f"of total impressions ({deep_impressions:,} of {total_impressions:,}). "
            f"{deep_queries:,} queries rank beyond position 50, generating only "
            f"{deep_clicks:,} clicks. "
            f"{'High deep-page impression share suggests significant content is ranking too far back to drive traffic.' if deep_share > 20 else 'Deep-page impression share is within normal bounds.'}"
        )

        display_df = (
            deep
            .sort_values("impressions", ascending=False)
            [["query", "impressions", "clicks", "position", "ctr"]]
            .head(25)
        )

        recommendations = []
        if deep_share > 10:
            recommendations.extend([
                "Review deep-ranking queries for relevance — some may indicate content that Google considers marginally relevant.",
                "Consider consolidating thin or duplicate content that ranks deep but does not add value.",
                "For high-impression deep queries, create or improve dedicated content to compete more effectively.",
                "Evaluate whether these deep impressions are inflating overall impression counts without contributing traffic.",
            ])
        else:
            recommendations.append(
                "Deep-page impression share is low, indicating most visibility comes from competitive positions. Continue optimizing mid-range queries."
            )

        return self.create_result(
            metric_id=71,
            severity=severity,
            summary=summary,
            computed_value=round(deep_share, 2),
            affected_count=deep_queries,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "deep_impressions": int(deep_impressions),
                "total_impressions": int(total_impressions),
                "deep_queries": deep_queries,
                "deep_clicks": int(deep_clicks),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 72 — Impression-to-Click Funnel Loss Rate
    # ------------------------------------------------------------------ #
    def metric_impression_to_click_funnel_loss_rate(self) -> MetricResult:
        """Compare (impressions - clicks)/impressions per page between current and previous 30d.

        Reports URLs where the funnel loss worsened (loss rate increased).
        HIGH if avg loss rate > 95%.
        """
        df_90d = self.get_df("page_date_90d")
        df_30d = self.get_df("page_date_30d")

        if df_90d.empty:
            return self._error_result(72, "No page-date data available")

        df_90d = df_90d.copy()
        df_90d["date"] = pd.to_datetime(df_90d["date"])

        max_date = df_90d["date"].max()
        current_start = max_date - timedelta(days=29)
        prev_start = max_date - timedelta(days=59)
        prev_end = max_date - timedelta(days=30)

        # Current 30d aggregation per page
        current = df_90d[df_90d["date"] >= current_start].groupby("page").agg(
            curr_impressions=("impressions", "sum"),
            curr_clicks=("clicks", "sum"),
        ).reset_index()

        # Previous 30d aggregation per page
        previous = df_90d[
            (df_90d["date"] >= prev_start) & (df_90d["date"] <= prev_end)
        ].groupby("page").agg(
            prev_impressions=("impressions", "sum"),
            prev_clicks=("clicks", "sum"),
        ).reset_index()

        merged = current.merge(previous, on="page", how="inner")
        if merged.empty:
            return self._error_result(72, "No pages found with data in both periods")

        # Compute funnel loss rate per page for each period
        merged["curr_loss_rate"] = (
            (merged["curr_impressions"] - merged["curr_clicks"])
            / merged["curr_impressions"]
        ).clip(0, 1)
        merged["prev_loss_rate"] = (
            (merged["prev_impressions"] - merged["prev_clicks"])
            / merged["prev_impressions"]
        ).clip(0, 1)

        # Identify pages where loss rate worsened
        merged["loss_change"] = merged["curr_loss_rate"] - merged["prev_loss_rate"]
        worsened = merged[merged["loss_change"] > 0].sort_values(
            "loss_change", ascending=False
        )

        avg_curr_loss = merged["curr_loss_rate"].mean() * 100
        avg_prev_loss = merged["prev_loss_rate"].mean() * 100
        worsened_count = len(worsened)
        total_pages = len(merged)

        if avg_curr_loss > 95:
            severity = Severity.HIGH
        elif avg_curr_loss > 90:
            severity = Severity.MEDIUM
        elif avg_curr_loss > 85:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        trend = (
            TrendDirection.DECLINING
            if avg_curr_loss > avg_prev_loss
            else TrendDirection.IMPROVING
            if avg_curr_loss < avg_prev_loss
            else TrendDirection.STABLE
        )

        summary = (
            f"Average impression-to-click funnel loss rate is {avg_curr_loss:.1f}% "
            f"(previous period: {avg_prev_loss:.1f}%). "
            f"{worsened_count:,} of {total_pages:,} pages saw worsening funnel loss. "
            f"{'Extremely high loss rate means nearly all impressions fail to convert to clicks.' if avg_curr_loss > 95 else 'Funnel loss is within typical range for organic search.'}"
        )

        # Build display table of worsened pages
        if not worsened.empty:
            display = worsened.copy()
            display["curr_loss_pct"] = (display["curr_loss_rate"] * 100).round(2)
            display["prev_loss_pct"] = (display["prev_loss_rate"] * 100).round(2)
            display["change_pct"] = (display["loss_change"] * 100).round(2)
            display_df = display[
                ["page", "curr_impressions", "curr_clicks", "curr_loss_pct",
                 "prev_loss_pct", "change_pct"]
            ].head(25)
        else:
            display_df = None

        recommendations = []
        if avg_curr_loss > 90:
            recommendations.extend([
                "Audit title tags and meta descriptions on highest-loss pages to improve click appeal.",
                "Check if SERP features are suppressing organic click-through on these pages.",
                "Improve content relevance for the queries driving impressions to reduce intent mismatch.",
                "Consider adding structured data to increase listing prominence and visual appeal in SERPs.",
            ])
        else:
            recommendations.append(
                "Funnel loss rate is typical. Continue optimizing snippets and content relevance for pages with the highest worsening trend."
            )

        return self.create_result(
            metric_id=72,
            severity=severity,
            summary=summary,
            computed_value=round(avg_curr_loss, 2),
            affected_count=worsened_count,
            data_table=display_df,
            recommendations=recommendations,
            trend_direction=trend,
            details={
                "avg_current_loss_rate": round(avg_curr_loss, 2),
                "avg_previous_loss_rate": round(avg_prev_loss, 2),
                "worsened_pages": worsened_count,
                "total_pages": total_pages,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 73 — New vs Returning Query Impression Split
    # ------------------------------------------------------------------ #
    def metric_new_vs_returning_query_impression_split(self) -> MetricResult:
        """Impression share of queries appearing in last 30d but not in previous 30-60d."""
        df_90d = self.get_df("query_date_90d")
        df_30d = self.get_df("query_date_30d")

        if df_90d.empty:
            return self._error_result(73, "No query-date data available")

        df_90d = df_90d.copy()
        df_90d["date"] = pd.to_datetime(df_90d["date"])

        max_date = df_90d["date"].max()
        current_start = max_date - timedelta(days=29)
        prev_start = max_date - timedelta(days=59)
        prev_end = max_date - timedelta(days=30)

        # Current 30d queries
        current_data = df_90d[df_90d["date"] >= current_start]
        current_queries = set(current_data["query"].unique())

        # Previous 30d queries (30-60 days ago)
        prev_queries = set(
            df_90d[
                (df_90d["date"] >= prev_start) & (df_90d["date"] <= prev_end)
            ]["query"].unique()
        )

        if not current_queries:
            return self._error_result(73, "No queries found in the current 30-day period")

        new_queries = current_queries - prev_queries
        returning_queries = current_queries & prev_queries

        # Get impression data for new and returning queries
        current_agg = (
            current_data.groupby("query")["impressions"]
            .sum()
            .reset_index()
        )
        total_impressions = current_agg["impressions"].sum()
        if total_impressions == 0:
            return self._error_result(73, "No impressions recorded in current period")

        new_query_data = current_agg[current_agg["query"].isin(new_queries)]
        returning_query_data = current_agg[current_agg["query"].isin(returning_queries)]

        new_impressions = new_query_data["impressions"].sum()
        returning_impressions = returning_query_data["impressions"].sum()

        new_share = (new_impressions / total_impressions * 100)
        returning_share = (returning_impressions / total_impressions * 100)

        new_count = len(new_queries)
        returning_count = len(returning_queries)
        total_current = len(current_queries)

        severity = Severity.INSIGHT

        summary = (
            f"New queries (not seen in previous 30d) account for {new_share:.1f}% "
            f"of current impressions ({new_impressions:,} of {total_impressions:,}). "
            f"{new_count:,} new queries vs {returning_count:,} returning queries "
            f"({total_current:,} total). "
            f"{'High new-query share indicates expanding topical reach or seasonal/trending topics.' if new_share > 40 else 'Returning queries drive most impressions, indicating stable keyword footprint.'}"
        )

        # Show top new queries by impressions
        display_df = (
            new_query_data
            .sort_values("impressions", ascending=False)
            .head(25)
            .copy()
        )
        if not display_df.empty:
            display_df["status"] = "new"

        trend = (
            TrendDirection.IMPROVING
            if new_share > 30
            else TrendDirection.STABLE
        )

        recommendations = [
            "Analyze new queries to identify emerging topics or search trends you can capitalize on with dedicated content.",
            "Determine if new queries come from existing content gaining new visibility or from recently published content.",
            "Monitor returning query impression trends to ensure established rankings remain stable.",
            "Create content specifically targeting high-impression new queries to solidify rankings.",
        ]

        return self.create_result(
            metric_id=73,
            severity=severity,
            summary=summary,
            computed_value=round(new_share, 2),
            affected_count=new_count,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            trend_direction=trend,
            details={
                "new_queries": new_count,
                "returning_queries": returning_count,
                "new_impression_share": round(new_share, 2),
                "returning_impression_share": round(returning_share, 2),
                "new_impressions": int(new_impressions),
                "returning_impressions": int(returning_impressions),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 74 — Rich Result Impression Rate
    # ------------------------------------------------------------------ #
    def metric_rich_result_impression_rate(self) -> MetricResult:
        """Total rich result impressions (all searchAppearance types) vs total web impressions."""
        df_sa = self.get_df("search_appearance_90d")
        df_sa_page = self.get_df("search_appearance_page_90d")

        if df_sa.empty:
            return self._error_result(74, "No search appearance data available")

        # Total impressions from all search appearance types
        rich_impressions = df_sa["impressions"].sum()
        rich_clicks = df_sa["clicks"].sum()

        # Get total web impressions from page_90d for the denominator
        df_page = self.get_df("page_90d")
        if df_page.empty:
            total_web_impressions = rich_impressions
        else:
            total_web_impressions = df_page["impressions"].sum()

        if total_web_impressions == 0:
            return self._error_result(74, "No impressions recorded")

        rich_rate = (rich_impressions / total_web_impressions * 100)

        # Break down by search appearance type
        type_breakdown = (
            df_sa.groupby("searchAppearance")
            .agg(impressions=("impressions", "sum"), clicks=("clicks", "sum"))
            .reset_index()
            .sort_values("impressions", ascending=False)
        )
        type_breakdown["share_pct"] = (
            type_breakdown["impressions"] / total_web_impressions * 100
        ).round(2)

        num_types = len(type_breakdown)

        severity = Severity.INSIGHT

        summary = (
            f"Rich result impressions total {rich_impressions:,} across "
            f"{num_types} search appearance types, representing {rich_rate:.1f}% "
            f"of total web impressions ({total_web_impressions:,}). "
            f"Rich results generated {rich_clicks:,} clicks. "
            f"{'Strong rich result presence enhances SERP visibility.' if rich_rate > 10 else 'Limited rich result presence — expanding structured data could increase visibility.'}"
        )

        # Build display table from type breakdown and page-level data
        if not df_sa_page.empty:
            page_rich = (
                df_sa_page.groupby("page")
                .agg(rich_impressions=("impressions", "sum"), rich_clicks=("clicks", "sum"))
                .reset_index()
                .sort_values("rich_impressions", ascending=False)
            )
            display_df = page_rich.head(25)
        else:
            display_df = type_breakdown.head(25)

        recommendations = [
            "Add structured data (FAQ, HowTo, Product, Recipe, etc.) to pages that lack rich result eligibility.",
            "Monitor Search Console's enhancements report for structured data errors that may prevent rich results.",
            "Identify top-performing rich result types and expand their use across additional relevant pages.",
            "Test different structured data types to determine which yield the highest CTR improvement.",
        ]

        return self.create_result(
            metric_id=74,
            severity=severity,
            summary=summary,
            computed_value=round(rich_rate, 2),
            affected_count=num_types,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "rich_impressions": int(rich_impressions),
                "rich_clicks": int(rich_clicks),
                "total_web_impressions": int(total_web_impressions),
                "rich_rate_pct": round(rich_rate, 2),
                "search_appearance_types": num_types,
                "type_breakdown": type_breakdown.to_dict(orient="records") if len(type_breakdown) <= 20 else None,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 75 — Video Result Impression Share
    # ------------------------------------------------------------------ #
    def metric_video_result_impression_share(self) -> MetricResult:
        """Total video search impressions vs total web impressions."""
        df_video = self.get_df("page_video_90d")

        # Get total web impressions
        df_page = self.get_df("page_90d")
        if df_page.empty:
            return self._error_result(75, "No page-level web data available for comparison")

        total_web_impressions = df_page["impressions"].sum()
        if total_web_impressions == 0:
            return self._error_result(75, "No web impressions recorded")

        if df_video.empty:
            return self.create_result(
                metric_id=75,
                severity=Severity.INSIGHT,
                summary=(
                    "No video search impressions found in the last 90 days. "
                    "The site has no visibility in Google video search results."
                ),
                computed_value=0.0,
                affected_count=0,
                recommendations=[
                    "Consider creating video content (tutorials, product demos, explainers) to capture video search impressions.",
                    "If you have video content, ensure proper video schema markup and XML video sitemaps are in place.",
                    "Host videos on your domain or use YouTube embeds with proper structured data to appear in video search.",
                ],
                details={
                    "video_impressions": 0,
                    "total_web_impressions": int(total_web_impressions),
                },
            )

        video_impressions = df_video["impressions"].sum()
        video_clicks = df_video["clicks"].sum()
        video_share = (video_impressions / total_web_impressions * 100)
        video_pages = len(df_video)

        video_ctr = (
            (video_clicks / video_impressions * 100)
            if video_impressions > 0 else 0.0
        )

        severity = Severity.INSIGHT

        summary = (
            f"Video search impressions total {video_impressions:,} across "
            f"{video_pages:,} pages, representing {video_share:.1f}% of total "
            f"web impressions ({total_web_impressions:,}). Video search CTR is "
            f"{video_ctr:.2f}% with {video_clicks:,} clicks. "
            f"{'Video search is a meaningful traffic channel.' if video_share > 5 else 'Video search is a minor channel for this site.'}"
        )

        display_df = (
            df_video
            .sort_values("impressions", ascending=False)
            [["page", "impressions", "clicks", "position", "ctr"]]
            .head(25)
        )

        recommendations = [
            "Optimize video titles, descriptions, and thumbnails to improve CTR in video search results.",
            "Add VideoObject schema markup to all pages with embedded video content.",
            "Create a video XML sitemap to help Google discover and index video content.",
            "Analyze which video topics drive the most impressions and create more content in those areas.",
        ]

        return self.create_result(
            metric_id=75,
            severity=severity,
            summary=summary,
            computed_value=round(video_share, 2),
            affected_count=video_pages,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "video_impressions": int(video_impressions),
                "video_clicks": int(video_clicks),
                "total_web_impressions": int(total_web_impressions),
                "video_share_pct": round(video_share, 2),
                "video_ctr": round(video_ctr, 2),
                "video_pages": video_pages,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 76 — Image Result Impression Share
    # ------------------------------------------------------------------ #
    def metric_image_result_impression_share(self) -> MetricResult:
        """Total image search impressions vs total web impressions."""
        df_image = self.get_df("page_image_90d")

        # Get total web impressions
        df_page = self.get_df("page_90d")
        if df_page.empty:
            return self._error_result(76, "No page-level web data available for comparison")

        total_web_impressions = df_page["impressions"].sum()
        if total_web_impressions == 0:
            return self._error_result(76, "No web impressions recorded")

        if df_image.empty:
            return self.create_result(
                metric_id=76,
                severity=Severity.INSIGHT,
                summary=(
                    "No image search impressions found in the last 90 days. "
                    "The site has no visibility in Google image search results."
                ),
                computed_value=0.0,
                affected_count=0,
                recommendations=[
                    "Add descriptive alt text to all images to improve image search discoverability.",
                    "Use high-quality, original images rather than stock photos when possible.",
                    "Implement image XML sitemaps to help Google discover and index image content.",
                    "Optimize image file names with descriptive, keyword-relevant names.",
                ],
                details={
                    "image_impressions": 0,
                    "total_web_impressions": int(total_web_impressions),
                },
            )

        image_impressions = df_image["impressions"].sum()
        image_clicks = df_image["clicks"].sum()
        image_share = (image_impressions / total_web_impressions * 100)
        image_pages = len(df_image)

        image_ctr = (
            (image_clicks / image_impressions * 100)
            if image_impressions > 0 else 0.0
        )

        severity = Severity.INSIGHT

        summary = (
            f"Image search impressions total {image_impressions:,} across "
            f"{image_pages:,} pages, representing {image_share:.1f}% of total "
            f"web impressions ({total_web_impressions:,}). Image search CTR is "
            f"{image_ctr:.2f}% with {image_clicks:,} clicks. "
            f"{'Image search is a significant discovery channel.' if image_share > 10 else 'Image search contributes modestly to overall visibility.'}"
        )

        display_df = (
            df_image
            .sort_values("impressions", ascending=False)
            [["page", "impressions", "clicks", "position", "ctr"]]
            .head(25)
        )

        recommendations = [
            "Add descriptive, keyword-rich alt text to all images to improve image search rankings.",
            "Use next-gen image formats (WebP, AVIF) with proper fallbacks for better performance and indexing.",
            "Create an image sitemap to improve Google's ability to discover and index image content.",
            "Optimize image file sizes for faster loading without sacrificing quality, improving both user experience and crawl efficiency.",
        ]

        return self.create_result(
            metric_id=76,
            severity=severity,
            summary=summary,
            computed_value=round(image_share, 2),
            affected_count=image_pages,
            data_table=display_df if not display_df.empty else None,
            recommendations=recommendations,
            details={
                "image_impressions": int(image_impressions),
                "image_clicks": int(image_clicks),
                "total_web_impressions": int(total_web_impressions),
                "image_share_pct": round(image_share, 2),
                "image_ctr": round(image_ctr, 2),
                "image_pages": image_pages,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 77 — News/Discover Impression Share
    # ------------------------------------------------------------------ #
    def metric_news_discover_impression_share(self) -> MetricResult:
        """Combined Discover + News impressions vs total web impressions."""
        df_discover = self.get_df("page_discover_90d")
        df_news = self.get_df("page_news_90d")

        # Get total web impressions
        df_page = self.get_df("page_90d")
        if df_page.empty:
            return self._error_result(77, "No page-level web data available for comparison")

        total_web_impressions = df_page["impressions"].sum()
        if total_web_impressions == 0:
            return self._error_result(77, "No web impressions recorded")

        # Discover data
        discover_impressions = df_discover["impressions"].sum() if not df_discover.empty else 0
        discover_clicks = df_discover["clicks"].sum() if not df_discover.empty else 0
        discover_pages = len(df_discover) if not df_discover.empty else 0

        # News data
        news_impressions = df_news["impressions"].sum() if not df_news.empty else 0
        news_clicks = df_news["clicks"].sum() if not df_news.empty else 0
        news_pages = len(df_news) if not df_news.empty else 0

        combined_impressions = discover_impressions + news_impressions
        combined_clicks = discover_clicks + news_clicks
        combined_share = (combined_impressions / total_web_impressions * 100)

        if combined_impressions == 0:
            return self.create_result(
                metric_id=77,
                severity=Severity.INSIGHT,
                summary=(
                    "No Discover or News impressions found in the last 90 days. "
                    "The site has no visibility in Google Discover or Google News."
                ),
                computed_value=0.0,
                affected_count=0,
                recommendations=[
                    "Publish timely, high-quality content with compelling images to become eligible for Google Discover.",
                    "Apply for Google News inclusion if you publish news or editorial content regularly.",
                    "Use high-resolution images (at least 1200px wide) to improve Discover eligibility.",
                    "Focus on E-E-A-T signals to build authority in your topic areas.",
                ],
                details={
                    "discover_impressions": 0,
                    "news_impressions": 0,
                    "total_web_impressions": int(total_web_impressions),
                },
            )

        severity = Severity.INSIGHT

        discover_share = (discover_impressions / total_web_impressions * 100) if total_web_impressions > 0 else 0.0
        news_share = (news_impressions / total_web_impressions * 100) if total_web_impressions > 0 else 0.0
        combined_ctr = (
            (combined_clicks / combined_impressions * 100)
            if combined_impressions > 0 else 0.0
        )

        summary = (
            f"Discover + News impressions total {combined_impressions:,}, representing "
            f"{combined_share:.1f}% of web impressions ({total_web_impressions:,}). "
            f"Discover: {discover_impressions:,} impressions across {discover_pages:,} pages. "
            f"News: {news_impressions:,} impressions across {news_pages:,} pages. "
            f"Combined CTR is {combined_ctr:.2f}% with {combined_clicks:,} clicks."
        )

        # Build combined display table
        parts = []
        if not df_discover.empty:
            disc_display = df_discover[["page", "impressions", "clicks"]].copy()
            disc_display["source"] = "discover"
            parts.append(disc_display)
        if not df_news.empty:
            news_display = df_news[["page", "impressions", "clicks"]].copy()
            news_display["source"] = "news"
            parts.append(news_display)

        if parts:
            display_df = (
                pd.concat(parts, ignore_index=True)
                .sort_values("impressions", ascending=False)
                .head(25)
            )
        else:
            display_df = None

        recommendations = [
            "Publish fresh, high-quality content regularly to maintain and grow Discover/News presence.",
            "Use compelling, high-resolution images (1200px+) as the primary image for articles — this strongly affects Discover performance.",
            "Focus on E-E-A-T (Experience, Expertise, Authority, Trustworthiness) to strengthen News/Discover eligibility.",
            "Monitor which topics and content formats perform best in Discover/News and produce more of that content.",
        ]

        return self.create_result(
            metric_id=77,
            severity=severity,
            summary=summary,
            computed_value=round(combined_share, 2),
            affected_count=discover_pages + news_pages,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "discover_impressions": int(discover_impressions),
                "discover_clicks": int(discover_clicks),
                "discover_pages": discover_pages,
                "discover_share_pct": round(discover_share, 2),
                "news_impressions": int(news_impressions),
                "news_clicks": int(news_clicks),
                "news_pages": news_pages,
                "news_share_pct": round(news_share, 2),
                "combined_share_pct": round(combined_share, 2),
                "combined_ctr": round(combined_ctr, 2),
                "total_web_impressions": int(total_web_impressions),
            },
        )
