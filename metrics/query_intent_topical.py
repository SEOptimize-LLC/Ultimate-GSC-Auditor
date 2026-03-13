"""Query Intent & Topical metrics (51-60).

Analyzes query intent distribution, long-tail vs head term balance,
question-format queries, diversity scores, overlap rates, and
seasonal concentration patterns.
"""

import logging
import math
from typing import Optional

import numpy as np
import pandas as pd

from metrics.base_metric import BaseMetricGroup
from models.metric_result import MetricResult, Severity, TrendDirection

logger = logging.getLogger(__name__)

# Words that mark a query as question-format
_QUESTION_STARTERS = {"who", "what", "where", "when", "why", "how"}


class QueryIntentTopicalMetrics(BaseMetricGroup):
    """Metrics 51-60: Query Intent & Topical analysis."""

    METRIC_REGISTRY: dict[int, str] = {
        51: "metric_informational_query_share",
        52: "metric_transactional_query_share",
        53: "metric_navigational_query_share",
        54: "metric_long_tail_query_rate",
        55: "metric_head_term_query_rate",
        56: "metric_question_format_query_share",
        57: "metric_query_diversity_score",
        58: "metric_single_impression_query_rate",
        59: "metric_query_overlap_rate_across_urls",
        60: "metric_seasonal_query_concentration",
    }

    # ------------------------------------------------------------------ #
    # Helper: intent breakdown
    # ------------------------------------------------------------------ #
    def _compute_intent_breakdown(
        self, df: pd.DataFrame
    ) -> dict[str, dict]:
        """Classify every query by intent and compute per-intent stats.

        Returns a dict keyed by intent label with counts, share,
        avg CTR, and avg position.
        """
        df = df.copy()
        df["intent"] = df["query"].apply(self.get_query_intent)
        # Queries without AI classification get "unclassified"
        df["intent"] = df["intent"].fillna("unclassified")

        total = len(df)
        breakdown: dict[str, dict] = {}

        for intent, grp in df.groupby("intent"):
            count = len(grp)
            share = (count / total * 100) if total > 0 else 0.0
            avg_ctr = grp["ctr"].mean() if "ctr" in grp.columns else 0.0
            avg_pos = grp["position"].mean() if "position" in grp.columns else 0.0
            total_clicks = grp["clicks"].sum() if "clicks" in grp.columns else 0
            total_impressions = grp["impressions"].sum() if "impressions" in grp.columns else 0
            breakdown[str(intent)] = {
                "count": count,
                "share_pct": round(share, 2),
                "avg_ctr": round(float(avg_ctr), 4),
                "avg_position": round(float(avg_pos), 2),
                "total_clicks": int(total_clicks),
                "total_impressions": int(total_impressions),
            }

        return breakdown

    # ------------------------------------------------------------------ #
    # Metric 51 — Informational Query Share
    # ------------------------------------------------------------------ #
    def metric_informational_query_share(self) -> MetricResult:
        """Share of queries classified as informational intent."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(51, "No query data available")

        breakdown = self._compute_intent_breakdown(df)
        total_queries = len(df)

        info = breakdown.get("informational", {})
        info_count = info.get("count", 0)
        info_share = info.get("share_pct", 0.0)
        info_avg_ctr = info.get("avg_ctr", 0.0)
        info_avg_pos = info.get("avg_position", 0.0)

        severity = Severity.INSIGHT

        # Build a summary table of all intents for context
        rows = []
        for intent_name, stats in sorted(
            breakdown.items(), key=lambda x: x[1]["count"], reverse=True
        ):
            rows.append({
                "intent": intent_name,
                "query_count": stats["count"],
                "share_pct": stats["share_pct"],
                "avg_ctr": round(stats["avg_ctr"] * 100, 2),
                "avg_position": stats["avg_position"],
                "total_clicks": stats["total_clicks"],
                "total_impressions": stats["total_impressions"],
            })
        display_df = pd.DataFrame(rows).head(25) if rows else None

        summary = (
            f"Informational queries account for {info_count:,} of {total_queries:,} "
            f"queries ({info_share:.1f}%). Avg CTR: {info_avg_ctr * 100:.2f}%, "
            f"avg position: {info_avg_pos:.1f}. "
            f"Informational content attracts top-of-funnel traffic and builds topical authority."
        )

        recommendations = []
        if info_share >= 50:
            recommendations.extend([
                "Strong informational presence. Ensure content includes internal links to transactional pages for funnel conversion.",
                "Add structured data (FAQ, HowTo) to informational pages to increase SERP feature visibility.",
                "Build email capture or lead magnets on high-traffic informational pages to monetize the audience.",
            ])
        elif info_share >= 20:
            recommendations.extend([
                "Informational query share is moderate. Identify gaps in informational content relative to competitors.",
                "Create supporting how-to guides and explainer content to build topical authority.",
            ])
        else:
            recommendations.extend([
                "Low informational query share may limit top-of-funnel visibility. Consider creating educational content.",
                "Audit competitor content to find informational topics in your niche that you are not covering.",
            ])

        return self.create_result(
            metric_id=51,
            severity=severity,
            summary=summary,
            computed_value=round(info_share, 2),
            affected_count=info_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "informational_queries": info_count,
                "total_queries": total_queries,
                "informational_share_pct": round(info_share, 2),
                "avg_ctr": round(info_avg_ctr, 4),
                "avg_position": round(info_avg_pos, 2),
                "intent_breakdown": breakdown,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 52 — Transactional Query Share
    # ------------------------------------------------------------------ #
    def metric_transactional_query_share(self) -> MetricResult:
        """Share of queries classified as transactional intent."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(52, "No query data available")

        breakdown = self._compute_intent_breakdown(df)
        total_queries = len(df)

        trans = breakdown.get("transactional", {})
        trans_count = trans.get("count", 0)
        trans_share = trans.get("share_pct", 0.0)
        trans_avg_ctr = trans.get("avg_ctr", 0.0)
        trans_avg_pos = trans.get("avg_position", 0.0)
        trans_clicks = trans.get("total_clicks", 0)

        # LOW if <10% — missed commerce opportunity
        if trans_share < 10:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        # Build intent summary table
        rows = []
        for intent_name, stats in sorted(
            breakdown.items(), key=lambda x: x[1]["count"], reverse=True
        ):
            rows.append({
                "intent": intent_name,
                "query_count": stats["count"],
                "share_pct": stats["share_pct"],
                "avg_ctr": round(stats["avg_ctr"] * 100, 2),
                "avg_position": stats["avg_position"],
                "total_clicks": stats["total_clicks"],
            })
        display_df = pd.DataFrame(rows).head(25) if rows else None

        if trans_share < 10:
            assessment = (
                "Low transactional query share suggests a missed commerce opportunity. "
                "Consider creating or optimizing product, pricing, and comparison pages."
            )
        else:
            assessment = (
                "Transactional query coverage is healthy, capturing commercial search intent."
            )

        summary = (
            f"Transactional queries account for {trans_count:,} of {total_queries:,} "
            f"queries ({trans_share:.1f}%), generating {trans_clicks:,} clicks. "
            f"Avg CTR: {trans_avg_ctr * 100:.2f}%, avg position: {trans_avg_pos:.1f}. "
            f"{assessment}"
        )

        recommendations = []
        if trans_share < 10:
            recommendations.extend([
                "Create dedicated landing pages targeting transactional keywords (buy, pricing, comparison, best, review).",
                "Optimize existing product/service pages with clear CTAs and commercial intent signals.",
                "Analyze competitor transactional content to identify gaps in your commercial keyword coverage.",
                "Add schema markup (Product, Offer, Review) to commercial pages for enhanced SERP listings.",
            ])
        elif trans_share < 25:
            recommendations.extend([
                "Moderate transactional presence. Expand commercial content with buyer guides and comparison pages.",
                "Ensure transactional pages have strong meta titles with action-oriented language to improve CTR.",
            ])
        else:
            recommendations.append(
                "Strong transactional query share. Focus on CTR optimization and conversion rate improvement for these pages."
            )

        return self.create_result(
            metric_id=52,
            severity=severity,
            summary=summary,
            computed_value=round(trans_share, 2),
            affected_count=trans_count,
            data_table=display_df,
            recommendations=recommendations,
            opportunity_value=(
                f"Potential to capture more commercial traffic"
                if trans_share < 10 else None
            ),
            details={
                "transactional_queries": trans_count,
                "total_queries": total_queries,
                "transactional_share_pct": round(trans_share, 2),
                "avg_ctr": round(trans_avg_ctr, 4),
                "avg_position": round(trans_avg_pos, 2),
                "total_transactional_clicks": trans_clicks,
                "intent_breakdown": breakdown,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 53 — Navigational Query Share
    # ------------------------------------------------------------------ #
    def metric_navigational_query_share(self) -> MetricResult:
        """Share of queries classified as navigational intent."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(53, "No query data available")

        breakdown = self._compute_intent_breakdown(df)
        total_queries = len(df)

        nav = breakdown.get("navigational", {})
        nav_count = nav.get("count", 0)
        nav_share = nav.get("share_pct", 0.0)
        nav_avg_ctr = nav.get("avg_ctr", 0.0)
        nav_avg_pos = nav.get("avg_position", 0.0)
        nav_clicks = nav.get("total_clicks", 0)

        severity = Severity.INSIGHT

        rows = []
        for intent_name, stats in sorted(
            breakdown.items(), key=lambda x: x[1]["count"], reverse=True
        ):
            rows.append({
                "intent": intent_name,
                "query_count": stats["count"],
                "share_pct": stats["share_pct"],
                "avg_ctr": round(stats["avg_ctr"] * 100, 2),
                "avg_position": stats["avg_position"],
                "total_clicks": stats["total_clicks"],
            })
        display_df = pd.DataFrame(rows).head(25) if rows else None

        summary = (
            f"Navigational queries account for {nav_count:,} of {total_queries:,} "
            f"queries ({nav_share:.1f}%), generating {nav_clicks:,} clicks. "
            f"Avg CTR: {nav_avg_ctr * 100:.2f}%, avg position: {nav_avg_pos:.1f}. "
            f"Navigational queries typically indicate brand searches or specific page lookups."
        )

        recommendations = []
        if nav_share >= 40:
            recommendations.extend([
                "High navigational share indicates strong brand awareness but also traffic dependency on brand name.",
                "Ensure all navigational queries lead to the correct landing pages with clear site links.",
                "Diversify organic traffic by growing informational and transactional query coverage.",
            ])
        elif nav_share >= 15:
            recommendations.extend([
                "Healthy navigational query share. Verify branded queries rank #1 and display sitelinks.",
                "Monitor for navigational queries leading to incorrect pages, which may confuse users.",
            ])
        else:
            recommendations.extend([
                "Low navigational share may indicate limited brand awareness in search.",
                "Strengthen brand presence through PR, content marketing, and consistent brand messaging.",
            ])

        return self.create_result(
            metric_id=53,
            severity=severity,
            summary=summary,
            computed_value=round(nav_share, 2),
            affected_count=nav_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "navigational_queries": nav_count,
                "total_queries": total_queries,
                "navigational_share_pct": round(nav_share, 2),
                "avg_ctr": round(nav_avg_ctr, 4),
                "avg_position": round(nav_avg_pos, 2),
                "total_navigational_clicks": nav_clicks,
                "intent_breakdown": breakdown,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 54 — Long-Tail Query Rate
    # ------------------------------------------------------------------ #
    def metric_long_tail_query_rate(self) -> MetricResult:
        """Percentage of queries with 4+ words (long-tail)."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(54, "No query data available")

        total_queries = len(df)
        df = df.copy()
        df["word_count"] = df["query"].str.split().str.len()

        long_tail = df[df["word_count"] >= 4]
        long_tail_count = len(long_tail)
        long_tail_pct = (long_tail_count / total_queries * 100) if total_queries > 0 else 0.0

        # Performance comparison
        long_tail_avg_ctr = long_tail["ctr"].mean() if not long_tail.empty else 0.0
        long_tail_avg_pos = long_tail["position"].mean() if not long_tail.empty else 0.0
        short_queries = df[df["word_count"] < 4]
        short_avg_ctr = short_queries["ctr"].mean() if not short_queries.empty else 0.0
        short_avg_pos = short_queries["position"].mean() if not short_queries.empty else 0.0

        long_tail_clicks = long_tail["clicks"].sum() if not long_tail.empty else 0
        total_clicks = df["clicks"].sum()
        long_tail_click_share = (
            long_tail_clicks / total_clicks * 100
        ) if total_clicks > 0 else 0.0

        # MEDIUM if <20% (missing long-tail opportunity)
        if long_tail_pct < 20:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{long_tail_count:,} of {total_queries:,} queries ({long_tail_pct:.1f}%) "
            f"are long-tail (4+ words), contributing {long_tail_click_share:.1f}% of clicks. "
            f"Long-tail avg CTR: {long_tail_avg_ctr * 100:.2f}% vs short-tail: {short_avg_ctr * 100:.2f}%. "
            f"Long-tail avg position: {long_tail_avg_pos:.1f} vs short-tail: {short_avg_pos:.1f}."
        )

        # Show top long-tail queries by clicks
        display_df = (
            long_tail
            .sort_values("clicks", ascending=False)
            [["query", "word_count", "clicks", "impressions", "position", "ctr"]]
            .head(25)
        ) if not long_tail.empty else None

        recommendations = []
        if long_tail_pct < 20:
            recommendations.extend([
                "Create in-depth, comprehensive content targeting specific long-tail queries related to your core topics.",
                "Add FAQ sections to existing pages to capture question-based long-tail queries.",
                "Analyze People Also Ask (PAA) boxes in your niche for long-tail content ideas.",
                "Use internal linking to connect related long-tail content pieces and build topical depth.",
            ])
        else:
            recommendations.extend([
                "Strong long-tail coverage. Continue creating detailed, specific content for niche queries.",
                "Monitor long-tail queries for conversion potential — these often signal high purchase intent.",
            ])

        return self.create_result(
            metric_id=54,
            severity=severity,
            summary=summary,
            computed_value=round(long_tail_pct, 2),
            affected_count=long_tail_count,
            data_table=display_df,
            recommendations=recommendations,
            opportunity_value=(
                f"Expand long-tail content to capture more specific search intent"
                if long_tail_pct < 20 else None
            ),
            details={
                "long_tail_queries": long_tail_count,
                "total_queries": total_queries,
                "long_tail_share_pct": round(long_tail_pct, 2),
                "long_tail_click_share_pct": round(long_tail_click_share, 2),
                "long_tail_avg_ctr": round(float(long_tail_avg_ctr), 4),
                "long_tail_avg_position": round(float(long_tail_avg_pos), 2),
                "short_tail_avg_ctr": round(float(short_avg_ctr), 4),
                "short_tail_avg_position": round(float(short_avg_pos), 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 55 — Head Term Query Rate
    # ------------------------------------------------------------------ #
    def metric_head_term_query_rate(self) -> MetricResult:
        """Percentage of queries with 1-2 words (head terms)."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(55, "No query data available")

        total_queries = len(df)
        df = df.copy()
        df["word_count"] = df["query"].str.split().str.len()

        head_terms = df[df["word_count"] <= 2]
        head_count = len(head_terms)
        head_pct = (head_count / total_queries * 100) if total_queries > 0 else 0.0

        head_clicks = head_terms["clicks"].sum() if not head_terms.empty else 0
        total_clicks = df["clicks"].sum()
        head_click_share = (
            head_clicks / total_clicks * 100
        ) if total_clicks > 0 else 0.0

        head_avg_ctr = head_terms["ctr"].mean() if not head_terms.empty else 0.0
        head_avg_pos = head_terms["position"].mean() if not head_terms.empty else 0.0
        head_impressions = head_terms["impressions"].sum() if not head_terms.empty else 0

        # Word count distribution
        wc_dist = (
            df.groupby("word_count")
            .agg(
                query_count=("query", "count"),
                total_clicks=("clicks", "sum"),
                avg_position=("position", "mean"),
                avg_ctr=("ctr", "mean"),
            )
            .reset_index()
            .sort_values("word_count")
        )
        wc_dist["avg_position"] = wc_dist["avg_position"].round(2)
        wc_dist["avg_ctr"] = (wc_dist["avg_ctr"] * 100).round(2)

        # HIGH if >60% (over-reliance on head terms)
        if head_pct > 60:
            severity = Severity.HIGH
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{head_count:,} of {total_queries:,} queries ({head_pct:.1f}%) are head "
            f"terms (1-2 words), accounting for {head_click_share:.1f}% of clicks "
            f"and {head_impressions:,} impressions. "
            f"Avg CTR: {head_avg_ctr * 100:.2f}%, avg position: {head_avg_pos:.1f}."
        )

        if head_pct > 60:
            summary += (
                " Over-reliance on head terms creates competitive risk — "
                "these queries are harder to rank for and more volatile."
            )

        display_df = wc_dist.head(25)

        recommendations = []
        if head_pct > 60:
            recommendations.extend([
                "Reduce dependency on highly competitive head terms by expanding long-tail content coverage.",
                "Create detailed content clusters around head term topics to capture related long-tail queries.",
                "Head terms are volatile in rankings — diversify with more specific, lower-competition queries.",
                "Analyze which head terms drive real conversions vs vanity traffic to prioritize efforts.",
            ])
        elif head_pct > 40:
            recommendations.extend([
                "Moderate head term reliance. Balance with long-tail content for more resilient organic traffic.",
                "Monitor head term rankings closely as these are most susceptible to algorithm and competitor changes.",
            ])
        else:
            recommendations.append(
                "Healthy distribution between head terms and longer queries. Continue balanced content strategy."
            )

        return self.create_result(
            metric_id=55,
            severity=severity,
            summary=summary,
            computed_value=round(head_pct, 2),
            affected_count=head_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "head_term_queries": head_count,
                "total_queries": total_queries,
                "head_term_share_pct": round(head_pct, 2),
                "head_term_click_share_pct": round(head_click_share, 2),
                "head_term_avg_ctr": round(float(head_avg_ctr), 4),
                "head_term_avg_position": round(float(head_avg_pos), 2),
                "head_term_impressions": int(head_impressions),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 56 — Question-Format Query Share
    # ------------------------------------------------------------------ #
    def metric_question_format_query_share(self) -> MetricResult:
        """Share of queries in question format (who/what/where/when/why/how or '?')."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(56, "No query data available")

        total_queries = len(df)
        df = df.copy()

        def _is_question(q: str) -> bool:
            q_lower = q.strip().lower()
            if "?" in q_lower:
                return True
            first_word = q_lower.split()[0] if q_lower.split() else ""
            return first_word in _QUESTION_STARTERS

        df["is_question"] = df["query"].apply(_is_question)
        question_queries = df[df["is_question"]]
        question_count = len(question_queries)
        question_pct = (question_count / total_queries * 100) if total_queries > 0 else 0.0

        question_clicks = question_queries["clicks"].sum() if not question_queries.empty else 0
        question_impressions = question_queries["impressions"].sum() if not question_queries.empty else 0
        question_avg_ctr = question_queries["ctr"].mean() if not question_queries.empty else 0.0
        question_avg_pos = question_queries["position"].mean() if not question_queries.empty else 0.0

        severity = Severity.INSIGHT

        summary = (
            f"{question_count:,} of {total_queries:,} queries ({question_pct:.1f}%) "
            f"are in question format, generating {question_clicks:,} clicks from "
            f"{question_impressions:,} impressions. "
            f"Avg CTR: {question_avg_ctr * 100:.2f}%, avg position: {question_avg_pos:.1f}."
        )

        # Show top question queries by impressions
        display_df = (
            question_queries
            .sort_values("impressions", ascending=False)
            [["query", "clicks", "impressions", "position", "ctr"]]
            .head(25)
        ) if not question_queries.empty else None

        recommendations = []
        if question_pct > 10:
            recommendations.extend([
                "Strong question-query presence signals featured snippet opportunities. Optimize content with direct, concise answers.",
                "Add FAQ schema markup to pages ranking for question queries to win rich results.",
                "Create dedicated FAQ or Q&A sections targeting the most common question patterns.",
                "Analyze People Also Ask (PAA) results for your question queries to find additional content opportunities.",
            ])
        else:
            recommendations.extend([
                "Low question-format query share. Consider creating FAQ and how-to content to capture question-based searches.",
                "Research question-based keywords in your niche using tools like AnswerThePublic or PAA analysis.",
                "Adding FAQ sections to existing pages can attract question queries without creating new content.",
            ])

        return self.create_result(
            metric_id=56,
            severity=severity,
            summary=summary,
            computed_value=round(question_pct, 2),
            affected_count=question_count,
            data_table=display_df,
            recommendations=recommendations,
            opportunity_value=(
                f"{question_count:,} question queries — potential featured snippet targets"
                if question_pct > 10 else None
            ),
            details={
                "question_queries": question_count,
                "total_queries": total_queries,
                "question_share_pct": round(question_pct, 2),
                "question_clicks": int(question_clicks),
                "question_impressions": int(question_impressions),
                "avg_ctr": round(float(question_avg_ctr), 4),
                "avg_position": round(float(question_avg_pos), 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 57 — Query Diversity Score
    # ------------------------------------------------------------------ #
    def metric_query_diversity_score(self) -> MetricResult:
        """Shannon entropy of click distribution across queries, normalized 0-100."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(57, "No query data available")

        # Only consider queries with clicks
        clicking = df[df["clicks"] > 0].copy()
        if clicking.empty:
            return self.create_result(
                metric_id=57,
                severity=Severity.HIGH,
                summary="No queries generated clicks — diversity score cannot be computed.",
                computed_value=0.0,
                recommendations=[
                    "Investigate why no queries are generating clicks. Review rankings, CTR, and content quality.",
                ],
            )

        total_clicks = clicking["clicks"].sum()
        clicking["click_share"] = clicking["clicks"] / total_clicks
        num_queries = len(clicking)

        # Shannon entropy: H = -sum(p * log2(p))
        entropy = -1.0 * (clicking["click_share"] * np.log2(clicking["click_share"])).sum()

        # Maximum entropy for n items = log2(n)
        max_entropy = math.log2(num_queries) if num_queries > 1 else 1.0

        # Normalize to 0-100
        diversity_score = (entropy / max_entropy * 100) if max_entropy > 0 else 0.0

        # LOW if <30 (few queries dominate)
        if diversity_score < 30:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        # Show top queries by click share to illustrate concentration
        top_queries = (
            clicking
            .sort_values("clicks", ascending=False)
            .head(25)
            .copy()
        )
        top_queries["click_share_pct"] = (top_queries["click_share"] * 100).round(2)
        display_df = top_queries[["query", "clicks", "impressions", "click_share_pct", "position"]]

        # Concentration stats
        top_5_share = clicking.nlargest(5, "clicks")["click_share"].sum() * 100
        top_10_share = clicking.nlargest(10, "clicks")["click_share"].sum() * 100

        summary = (
            f"Query diversity score is {diversity_score:.1f}/100 (Shannon entropy normalized). "
            f"{num_queries:,} queries generated clicks from {total_clicks:,} total clicks. "
            f"Top 5 queries capture {top_5_share:.1f}% and top 10 capture {top_10_share:.1f}% of clicks."
        )

        if diversity_score < 30:
            summary += (
                " Low diversity means a small number of queries dominate click traffic, "
                "creating fragility if those queries lose rankings."
            )

        recommendations = []
        if diversity_score < 30:
            recommendations.extend([
                "Click traffic is concentrated on very few queries. Diversify content to attract a broader range of queries.",
                "Create new content targeting related topics to reduce dependency on dominant queries.",
                "Analyze whether click-dominant queries are branded — high branded concentration may mask weak organic reach.",
                "Build supporting content around dominant query topics to create a wider query footprint.",
            ])
        elif diversity_score < 60:
            recommendations.extend([
                "Moderate query diversity. Continue expanding content coverage to attract more unique click-generating queries.",
                "Identify content gaps where competitors rank for queries you do not yet appear for.",
            ])
        else:
            recommendations.append(
                "Strong query diversity. Click traffic is well-distributed, reducing risk from single-query dependency."
            )

        return self.create_result(
            metric_id=57,
            severity=severity,
            summary=summary,
            computed_value=round(diversity_score, 2),
            affected_count=num_queries,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "diversity_score": round(diversity_score, 2),
                "shannon_entropy": round(float(entropy), 4),
                "max_entropy": round(max_entropy, 4),
                "clicking_queries": num_queries,
                "total_clicks": int(total_clicks),
                "top_5_click_share_pct": round(top_5_share, 2),
                "top_10_click_share_pct": round(top_10_share, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 58 — Single-Impression Query Rate
    # ------------------------------------------------------------------ #
    def metric_single_impression_query_rate(self) -> MetricResult:
        """Percentage of queries with exactly 1 impression."""
        df = self.get_df("query_90d")
        if df.empty:
            return self._error_result(58, "No query data available")

        total_queries = len(df)
        single_imp = df[df["impressions"] == 1]
        single_count = len(single_imp)
        single_pct = (single_count / total_queries * 100) if total_queries > 0 else 0.0

        # How many of these single-impression queries got a click?
        single_with_click = single_imp[single_imp["clicks"] > 0]
        single_click_count = len(single_with_click)

        # Position distribution of single-impression queries
        single_avg_pos = single_imp["position"].mean() if not single_imp.empty else 0.0

        # Severity thresholds
        if single_pct > 50:
            severity = Severity.HIGH
        elif single_pct > 35:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        summary = (
            f"{single_count:,} of {total_queries:,} queries ({single_pct:.1f}%) have "
            f"exactly 1 impression. {single_click_count:,} of those generated a click. "
            f"Avg position: {single_avg_pos:.1f}. "
        )
        if single_pct > 35:
            summary += (
                "A high single-impression rate often indicates peripheral rankings, "
                "rare/misspelled queries, or very low search volume terms."
            )
        else:
            summary += (
                "Single-impression queries are within normal range."
            )

        # Show sample of single-impression queries with best positions
        display_df = (
            single_imp
            .sort_values("position", ascending=True)
            [["query", "impressions", "clicks", "position"]]
            .head(25)
        ) if not single_imp.empty else None

        recommendations = []
        if single_pct > 50:
            recommendations.extend([
                "Many queries appear only once — review if the site is generating impressions for irrelevant, low-quality queries.",
                "Single-impression queries often inflate query counts without contributing traffic. Focus optimization on multi-impression queries.",
                "Check if thin or auto-generated pages are causing the site to appear for a high volume of rare queries.",
                "Filter out single-impression queries from performance analysis to get a clearer picture of meaningful organic reach.",
            ])
        elif single_pct > 35:
            recommendations.extend([
                "Moderate single-impression rate. These queries add noise to analysis but may include long-tail opportunities.",
                "Review single-impression queries with good positions for content expansion opportunities.",
            ])
        else:
            recommendations.append(
                "Single-impression query rate is normal. Most queries are generating sustained visibility."
            )

        return self.create_result(
            metric_id=58,
            severity=severity,
            summary=summary,
            computed_value=round(single_pct, 2),
            affected_count=single_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "single_impression_queries": single_count,
                "total_queries": total_queries,
                "single_impression_pct": round(single_pct, 2),
                "single_impression_with_click": single_click_count,
                "avg_position": round(float(single_avg_pos), 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 59 — Query Overlap Rate Across URLs
    # ------------------------------------------------------------------ #
    def metric_query_overlap_rate_across_urls(self) -> MetricResult:
        """Queries appearing on 2+ pages divided by total unique queries."""
        df = self.get_df("query_page_90d")
        if df.empty:
            return self._error_result(59, "No query-page data available")

        # Count how many distinct pages each query appears on
        query_page_counts = (
            df.groupby("query")["page"]
            .nunique()
            .reset_index()
            .rename(columns={"page": "page_count"})
        )

        total_unique_queries = len(query_page_counts)
        overlapping = query_page_counts[query_page_counts["page_count"] >= 2]
        overlap_count = len(overlapping)
        overlap_pct = (overlap_count / total_unique_queries * 100) if total_unique_queries > 0 else 0.0

        # Severity: HIGH if >40%
        if overlap_pct > 40:
            severity = Severity.HIGH
        elif overlap_pct > 25:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        # Enrich with click/impression data for the most overlapping queries
        top_overlapping = overlapping.sort_values("page_count", ascending=False).head(25)
        if not top_overlapping.empty:
            # Merge back with original data to get performance stats
            overlap_details = df[df["query"].isin(top_overlapping["query"])].copy()
            overlap_summary = (
                overlap_details
                .groupby("query")
                .agg(
                    page_count=("page", "nunique"),
                    total_clicks=("clicks", "sum"),
                    total_impressions=("impressions", "sum"),
                    avg_position=("position", "mean"),
                )
                .reset_index()
                .sort_values("page_count", ascending=False)
            )
            overlap_summary["avg_position"] = overlap_summary["avg_position"].round(2)
            display_df = overlap_summary.head(25)
        else:
            display_df = None

        # Avg pages per overlapping query
        avg_pages_per_overlap = overlapping["page_count"].mean() if not overlapping.empty else 0.0
        max_pages = overlapping["page_count"].max() if not overlapping.empty else 0

        summary = (
            f"{overlap_count:,} of {total_unique_queries:,} unique queries ({overlap_pct:.1f}%) "
            f"appear on 2 or more pages. Avg pages per overlapping query: {avg_pages_per_overlap:.1f}, "
            f"max: {max_pages}. "
        )
        if overlap_pct > 40:
            summary += (
                "High overlap suggests potential keyword cannibalization — "
                "multiple pages competing for the same queries can dilute rankings."
            )
        else:
            summary += "Overlap rate is within acceptable range."

        recommendations = []
        if overlap_pct > 40:
            recommendations.extend([
                "Audit high-overlap queries for keyword cannibalization — consolidate competing pages where appropriate.",
                "Use canonical tags or 301 redirects to signal Google which page should rank for each query.",
                "Implement a clear internal linking strategy to differentiate page intent for overlapping queries.",
                "Consider merging thin, overlapping pages into a single comprehensive resource.",
            ])
        elif overlap_pct > 25:
            recommendations.extend([
                "Moderate query overlap detected. Review top overlapping queries for potential cannibalization issues.",
                "Differentiate competing pages through unique content angles, headings, and internal link signals.",
            ])
        else:
            recommendations.append(
                "Query overlap is low, indicating clear topical differentiation between pages. Monitor for emerging overlaps."
            )

        return self.create_result(
            metric_id=59,
            severity=severity,
            summary=summary,
            computed_value=round(overlap_pct, 2),
            affected_count=overlap_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "overlapping_queries": overlap_count,
                "total_unique_queries": total_unique_queries,
                "overlap_rate_pct": round(overlap_pct, 2),
                "avg_pages_per_overlap": round(float(avg_pages_per_overlap), 2),
                "max_pages_for_single_query": int(max_pages),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 60 — Seasonal Query Concentration
    # ------------------------------------------------------------------ #
    def metric_seasonal_query_concentration(self) -> MetricResult:
        """Percentage of queries with high seasonality (CV of impressions across months >1.5)."""
        df = self.get_df("query_date_365d")
        if df.empty:
            return self._error_result(60, "No 365-day query-date data available")

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df["month"] = df["date"].dt.to_period("M")

        # Aggregate impressions per query per month
        monthly = (
            df.groupby(["query", "month"])["impressions"]
            .sum()
            .reset_index()
        )

        # Compute coefficient of variation per query
        # CV = std / mean; only for queries appearing in 3+ months to be meaningful
        query_stats = (
            monthly.groupby("query")["impressions"]
            .agg(["mean", "std", "count"])
            .reset_index()
        )
        query_stats.columns = ["query", "imp_mean", "imp_std", "month_count"]

        # Filter queries with at least 3 months of data
        multi_month = query_stats[query_stats["month_count"] >= 3].copy()

        if multi_month.empty:
            return self.create_result(
                metric_id=60,
                severity=Severity.INSIGHT,
                summary=(
                    "Insufficient monthly data to compute seasonality. "
                    "Most queries appear in fewer than 3 months."
                ),
                computed_value=0.0,
                recommendations=[
                    "Ensure 365-day data is available for accurate seasonality analysis.",
                ],
                details={"queries_with_3plus_months": 0},
            )

        # Fill NaN std with 0 (queries with identical impressions each month)
        multi_month["imp_std"] = multi_month["imp_std"].fillna(0.0)
        multi_month["cv"] = multi_month.apply(
            lambda row: (row["imp_std"] / row["imp_mean"]) if row["imp_mean"] > 0 else 0.0,
            axis=1,
        )

        total_analyzed = len(multi_month)
        seasonal = multi_month[multi_month["cv"] > 1.5]
        seasonal_count = len(seasonal)
        seasonal_pct = (seasonal_count / total_analyzed * 100) if total_analyzed > 0 else 0.0

        severity = Severity.INSIGHT

        # Build display table of most seasonal queries
        if not seasonal.empty:
            top_seasonal = seasonal.sort_values("cv", ascending=False).head(25).copy()
            top_seasonal["cv"] = top_seasonal["cv"].round(2)
            top_seasonal["imp_mean"] = top_seasonal["imp_mean"].round(0).astype(int)
            display_df = top_seasonal[["query", "cv", "imp_mean", "month_count"]]
            display_df = display_df.rename(columns={
                "cv": "coefficient_of_variation",
                "imp_mean": "avg_monthly_impressions",
                "month_count": "months_active",
            })
        else:
            display_df = None

        non_seasonal_count = total_analyzed - seasonal_count

        summary = (
            f"{seasonal_count:,} of {total_analyzed:,} analyzed queries ({seasonal_pct:.1f}%) "
            f"show strong seasonality (coefficient of variation > 1.5). "
            f"{non_seasonal_count:,} queries have stable impression patterns year-round. "
        )
        if seasonal_pct > 30:
            summary += (
                "High seasonal concentration means traffic may fluctuate significantly "
                "across the year — plan content calendars accordingly."
            )
        else:
            summary += "Most queries generate consistent impressions throughout the year."

        recommendations = []
        if seasonal_pct > 30:
            recommendations.extend([
                "Build a content calendar aligned with peak seasons for your top seasonal queries.",
                "Pre-publish and optimize seasonal content 2-3 months before peak periods to build authority.",
                "Diversify content to include more evergreen topics and reduce overall traffic seasonality.",
                "Use historical data to forecast traffic dips and plan marketing campaigns accordingly.",
            ])
        elif seasonal_pct > 10:
            recommendations.extend([
                "Some queries show seasonal patterns. Plan content updates and promotions around peak periods.",
                "Monitor seasonal queries for ranking drops before peak season — early optimization preserves traffic.",
            ])
        else:
            recommendations.append(
                "Low seasonality across queries. Traffic patterns are relatively stable year-round."
            )

        return self.create_result(
            metric_id=60,
            severity=severity,
            summary=summary,
            computed_value=round(seasonal_pct, 2),
            affected_count=seasonal_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "seasonal_queries": seasonal_count,
                "non_seasonal_queries": non_seasonal_count,
                "total_analyzed": total_analyzed,
                "seasonal_pct": round(seasonal_pct, 2),
                "cv_threshold": 1.5,
            },
        )
