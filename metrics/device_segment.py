"""Device & Segment metrics (49-50).

Analyzes mobile vs desktop performance gaps and impression
distribution across device types.
"""

import logging

import pandas as pd

from metrics.base_metric import BaseMetricGroup
from models.metric_result import MetricResult, Severity, TrendDirection

logger = logging.getLogger(__name__)


class DeviceSegmentMetrics(BaseMetricGroup):
    """Metrics 49-50: Device & Segment analysis."""

    METRIC_REGISTRY: dict[int, str] = {
        49: "metric_mobile_vs_desktop_ctr_gap",
        50: "metric_mobile_impression_share",
    }

    # ------------------------------------------------------------------ #
    # Metric 49 — Mobile vs Desktop CTR Gap
    # ------------------------------------------------------------------ #
    def metric_mobile_vs_desktop_ctr_gap(self) -> MetricResult:
        """Average CTR gap between desktop and mobile across queries and pages."""
        df_query = self.get_df("query_device_90d")
        df_page = self.get_df("page_device_90d")

        if df_query.empty and df_page.empty:
            return self._error_result(49, "No device-segmented data available")

        # --- Query-level CTR gap ---
        query_gap = None
        mobile_ctr_q = None
        desktop_ctr_q = None

        if not df_query.empty:
            df_query = df_query.copy()
            df_query["device"] = df_query["device"].str.upper()

            mobile_q = df_query[df_query["device"] == "MOBILE"]
            desktop_q = df_query[df_query["device"] == "DESKTOP"]

            if not mobile_q.empty and not desktop_q.empty:
                mobile_total_clicks_q = mobile_q["clicks"].sum()
                mobile_total_imp_q = mobile_q["impressions"].sum()
                desktop_total_clicks_q = desktop_q["clicks"].sum()
                desktop_total_imp_q = desktop_q["impressions"].sum()

                mobile_ctr_q = (
                    (mobile_total_clicks_q / mobile_total_imp_q * 100)
                    if mobile_total_imp_q > 0
                    else 0.0
                )
                desktop_ctr_q = (
                    (desktop_total_clicks_q / desktop_total_imp_q * 100)
                    if desktop_total_imp_q > 0
                    else 0.0
                )
                query_gap = desktop_ctr_q - mobile_ctr_q

        # --- Page-level CTR gap ---
        page_gap = None
        mobile_ctr_p = None
        desktop_ctr_p = None
        page_detail_df = None

        if not df_page.empty:
            df_page = df_page.copy()
            df_page["device"] = df_page["device"].str.upper()

            mobile_p = df_page[df_page["device"] == "MOBILE"]
            desktop_p = df_page[df_page["device"] == "DESKTOP"]

            if not mobile_p.empty and not desktop_p.empty:
                mobile_total_clicks_p = mobile_p["clicks"].sum()
                mobile_total_imp_p = mobile_p["impressions"].sum()
                desktop_total_clicks_p = desktop_p["clicks"].sum()
                desktop_total_imp_p = desktop_p["impressions"].sum()

                mobile_ctr_p = (
                    (mobile_total_clicks_p / mobile_total_imp_p * 100)
                    if mobile_total_imp_p > 0
                    else 0.0
                )
                desktop_ctr_p = (
                    (desktop_total_clicks_p / desktop_total_imp_p * 100)
                    if desktop_total_imp_p > 0
                    else 0.0
                )
                page_gap = desktop_ctr_p - mobile_ctr_p

                # Per-URL breakdown: compute CTR gap per page
                mobile_page_stats = (
                    mobile_p.groupby("page")
                    .agg(
                        mobile_clicks=("clicks", "sum"),
                        mobile_impressions=("impressions", "sum"),
                    )
                    .reset_index()
                )
                desktop_page_stats = (
                    desktop_p.groupby("page")
                    .agg(
                        desktop_clicks=("clicks", "sum"),
                        desktop_impressions=("impressions", "sum"),
                    )
                    .reset_index()
                )

                page_merged = mobile_page_stats.merge(
                    desktop_page_stats, on="page", how="outer"
                ).fillna(0)

                page_merged["mobile_ctr"] = (
                    page_merged["mobile_clicks"]
                    / page_merged["mobile_impressions"].replace(0, float("nan"))
                    * 100
                ).fillna(0).round(2)

                page_merged["desktop_ctr"] = (
                    page_merged["desktop_clicks"]
                    / page_merged["desktop_impressions"].replace(0, float("nan"))
                    * 100
                ).fillna(0).round(2)

                page_merged["ctr_gap_pp"] = (
                    page_merged["desktop_ctr"] - page_merged["mobile_ctr"]
                ).round(2)

                # Show pages with the largest mobile disadvantage
                page_detail_df = (
                    page_merged.sort_values("ctr_gap_pp", ascending=False)
                    [["page", "mobile_ctr", "desktop_ctr", "ctr_gap_pp",
                      "mobile_impressions", "desktop_impressions"]]
                    .head(25)
                )

        # Use query-level gap as primary; fall back to page-level
        primary_gap = query_gap if query_gap is not None else page_gap
        if primary_gap is None:
            return self._error_result(
                49, "Could not compute CTR gap — insufficient mobile or desktop data"
            )

        abs_gap = abs(primary_gap)

        if abs_gap > 5:
            severity = Severity.HIGH
        elif abs_gap > 3:
            severity = Severity.MEDIUM
        elif abs_gap > 1:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        # Determine direction of gap
        if primary_gap > 0:
            gap_description = (
                f"Desktop CTR is {primary_gap:.1f} percentage points higher than mobile"
            )
        elif primary_gap < 0:
            gap_description = (
                f"Mobile CTR is {abs(primary_gap):.1f} percentage points higher than desktop"
            )
        else:
            gap_description = "Mobile and desktop CTR are equal"

        # Build summary with available data
        parts = [f"{gap_description}."]
        if mobile_ctr_q is not None and desktop_ctr_q is not None:
            parts.append(
                f"Query-level CTR: mobile {mobile_ctr_q:.2f}% vs desktop {desktop_ctr_q:.2f}% "
                f"(gap: {query_gap:+.2f}pp)."
            )
        if mobile_ctr_p is not None and desktop_ctr_p is not None:
            parts.append(
                f"Page-level CTR: mobile {mobile_ctr_p:.2f}% vs desktop {desktop_ctr_p:.2f}% "
                f"(gap: {page_gap:+.2f}pp)."
            )
        if abs_gap > 3:
            parts.append(
                "A significant gap may indicate mobile UX issues, slow page speed, "
                "or unoptimized mobile SERP listings."
            )

        summary = " ".join(parts)

        # Count pages with gap > 3pp for affected_count
        affected = 0
        if page_detail_df is not None and not page_detail_df.empty:
            affected = int((page_detail_df["ctr_gap_pp"].abs() > 3).sum())

        recommendations = []
        if abs_gap > 3:
            recommendations.extend([
                "Audit mobile page speed and Core Web Vitals — slow mobile pages suppress click-through rates.",
                "Review mobile SERP appearance: ensure title tags and meta descriptions render fully on smaller screens.",
                "Check for mobile usability issues in Google Search Console (interstitials, viewport, touch targets).",
                "Test mobile-specific user experience — content layout, readability, and call-to-action visibility.",
                "Compare mobile vs desktop ranking positions for key queries to rule out position-driven CTR differences.",
            ])
        else:
            recommendations.append(
                "Mobile and desktop CTR are closely aligned. Continue monitoring "
                "for emerging gaps as Google's mobile-first indexing evolves."
            )

        return self.create_result(
            metric_id=49,
            severity=severity,
            summary=summary,
            computed_value=round(primary_gap, 2),
            affected_count=affected,
            data_table=page_detail_df,
            recommendations=recommendations,
            details={
                "query_level_gap_pp": round(query_gap, 2) if query_gap is not None else None,
                "page_level_gap_pp": round(page_gap, 2) if page_gap is not None else None,
                "mobile_ctr_query": round(mobile_ctr_q, 2) if mobile_ctr_q is not None else None,
                "desktop_ctr_query": round(desktop_ctr_q, 2) if desktop_ctr_q is not None else None,
                "mobile_ctr_page": round(mobile_ctr_p, 2) if mobile_ctr_p is not None else None,
                "desktop_ctr_page": round(desktop_ctr_p, 2) if desktop_ctr_p is not None else None,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 50 — Mobile Impression Share
    # ------------------------------------------------------------------ #
    def metric_mobile_impression_share(self) -> MetricResult:
        """Mobile impressions as a percentage of total impressions."""
        df = self.get_df("page_device_90d")
        if df.empty:
            return self._error_result(50, "No page-device data available")

        df = df.copy()
        df["device"] = df["device"].str.upper()

        # Aggregate impressions by device type
        device_totals = (
            df.groupby("device")["impressions"]
            .sum()
            .reset_index()
            .rename(columns={"impressions": "total_impressions"})
        )

        total_impressions = device_totals["total_impressions"].sum()
        if total_impressions == 0:
            return self._error_result(50, "No impressions recorded across any device")

        mobile_impressions = device_totals.loc[
            device_totals["device"] == "MOBILE", "total_impressions"
        ]
        mobile_imp = int(mobile_impressions.iloc[0]) if not mobile_impressions.empty else 0
        mobile_share = (mobile_imp / total_impressions * 100) if total_impressions > 0 else 0.0

        desktop_impressions = device_totals.loc[
            device_totals["device"] == "DESKTOP", "total_impressions"
        ]
        desktop_imp = int(desktop_impressions.iloc[0]) if not desktop_impressions.empty else 0
        desktop_share = (desktop_imp / total_impressions * 100) if total_impressions > 0 else 0.0

        tablet_impressions = device_totals.loc[
            device_totals["device"] == "TABLET", "total_impressions"
        ]
        tablet_imp = int(tablet_impressions.iloc[0]) if not tablet_impressions.empty else 0
        tablet_share = (tablet_imp / total_impressions * 100) if total_impressions > 0 else 0.0

        # Severity logic
        if mobile_share > 70:
            severity = Severity.INSIGHT
            assessment = (
                "This is a mobile-first site with the majority of search impressions from mobile devices. "
                "Mobile UX and page speed should be the top priority."
            )
        elif mobile_share < 30:
            severity = Severity.HIGH
            assessment = (
                "Desktop-heavy impression distribution may indicate mobile indexing or visibility issues. "
                "Investigate whether mobile rankings differ significantly from desktop."
            )
        elif mobile_share < 40:
            severity = Severity.MEDIUM
            assessment = (
                "Below-average mobile impression share. Most industries see 50-70% mobile traffic. "
                "Review mobile-specific ranking performance."
            )
        else:
            severity = Severity.INSIGHT
            assessment = (
                "Mobile impression share is within the typical range for most industries."
            )

        # Per-URL breakdown
        mobile_pages = df[df["device"] == "MOBILE"].copy()
        all_pages = (
            df.groupby("page")["impressions"]
            .sum()
            .reset_index()
            .rename(columns={"impressions": "total_impressions"})
        )
        mobile_page_stats = (
            mobile_pages.groupby("page")["impressions"]
            .sum()
            .reset_index()
            .rename(columns={"impressions": "mobile_impressions"})
        )

        page_breakdown = all_pages.merge(mobile_page_stats, on="page", how="left").fillna(0)
        page_breakdown["mobile_share_pct"] = (
            page_breakdown["mobile_impressions"]
            / page_breakdown["total_impressions"].replace(0, float("nan"))
            * 100
        ).fillna(0).round(1)

        # Sort by total impressions to show most impactful pages
        page_breakdown = page_breakdown.sort_values(
            "total_impressions", ascending=False
        )

        display_df = page_breakdown[
            ["page", "total_impressions", "mobile_impressions", "mobile_share_pct"]
        ].head(25)

        summary = (
            f"Mobile impressions account for {mobile_share:.1f}% of total "
            f"({mobile_imp:,} of {total_impressions:,}). "
            f"Desktop: {desktop_share:.1f}%, Tablet: {tablet_share:.1f}%. "
            f"{assessment}"
        )

        recommendations = []
        if mobile_share < 40:
            recommendations.extend([
                "Verify mobile-friendliness using Google's Mobile-Friendly Test and fix any reported issues.",
                "Check Core Web Vitals for mobile — poor scores can suppress mobile rankings and impressions.",
                "Compare mobile vs desktop rankings for key queries to identify mobile-specific ranking drops.",
                "Ensure responsive design works correctly and content is not hidden on mobile devices.",
                "Review Google Search Console's Mobile Usability report for crawling issues.",
            ])
        elif mobile_share > 70:
            recommendations.extend([
                "Prioritize mobile page speed optimization — this is a mobile-dominant site.",
                "Ensure AMP or mobile-optimized content is available for key landing pages.",
                "Consider mobile-specific UX improvements like tap targets, font sizes, and viewport handling.",
            ])
        else:
            recommendations.append(
                "Device distribution is balanced. Maintain mobile-first design practices "
                "and monitor for shifts in device-level performance."
            )

        return self.create_result(
            metric_id=50,
            severity=severity,
            summary=summary,
            computed_value=round(mobile_share, 2),
            affected_count=len(page_breakdown),
            data_table=display_df,
            recommendations=recommendations,
            benchmark_comparison=(
                "above" if mobile_share > 60 else "below" if mobile_share < 40 else "at"
            ),
            details={
                "mobile_share_pct": round(mobile_share, 2),
                "desktop_share_pct": round(desktop_share, 2),
                "tablet_share_pct": round(tablet_share, 2),
                "mobile_impressions": mobile_imp,
                "desktop_impressions": desktop_imp,
                "tablet_impressions": tablet_imp,
                "total_impressions": int(total_impressions),
            },
        )
