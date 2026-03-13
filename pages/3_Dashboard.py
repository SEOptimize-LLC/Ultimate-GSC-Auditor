"""Dashboard page — Health score, severity distribution, category summaries."""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

from models.metric_result import Severity
from models.data_shapes import METRIC_CATEGORIES


def _grade_color(grade: str) -> str:
    """Get color for health grade."""
    return {
        "A": "#28A745",
        "B": "#5CB85C",
        "C": "#FFC107",
        "D": "#FD7E14",
        "F": "#DC3545",
    }.get(grade, "#6C757D")


def _severity_bar_chart(severity_counts: dict):
    """Render severity distribution as a horizontal bar chart."""
    order = ["critical", "high", "medium", "low", "insight"]
    colors = {
        "critical": "#DC3545",
        "high": "#FD7E14",
        "medium": "#FFC107",
        "low": "#0D6EFD",
        "insight": "#6C757D",
    }

    data = []
    for sev in order:
        count = severity_counts.get(sev, 0)
        if count > 0:
            data.append({
                "Severity": sev.title(),
                "Count": count,
                "Color": colors[sev],
            })

    if not data:
        st.info("No findings to display.")
        return

    df = pd.DataFrame(data)
    fig = px.bar(
        df,
        x="Count",
        y="Severity",
        orientation="h",
        color="Severity",
        color_discrete_map={s.title(): colors[s] for s in order},
    )
    fig.update_layout(
        showlegend=False,
        height=200,
        margin=dict(l=0, r=0, t=10, b=0),
        xaxis_title="",
        yaxis_title="",
    )
    st.plotly_chart(fig, use_container_width=True)


def _worst_severity_in_category(results) -> Severity:
    """Get the worst severity from a list of MetricResults."""
    if not results:
        return Severity.INSIGHT
    return min(results, key=lambda r: r.severity.priority).severity


def _category_cards(results_by_category: dict):
    """Render category summary cards in a grid."""
    categories = list(METRIC_CATEGORIES.keys())
    cols_per_row = 3

    for row_start in range(0, len(categories), cols_per_row):
        cols = st.columns(cols_per_row)
        for col_idx, cat_name in enumerate(
            categories[row_start:row_start + cols_per_row]
        ):
            cat_results = results_by_category.get(cat_name, [])
            worst = _worst_severity_in_category(cat_results)
            finding_count = len(cat_results)

            sev_summary = {}
            for r in cat_results:
                sev_summary[r.severity.value] = (
                    sev_summary.get(r.severity.value, 0) + 1
                )

            with cols[col_idx]:
                border_color = worst.color
                st.markdown(
                    f"""<div style="
                        border-left: 4px solid {border_color};
                        padding: 12px 16px;
                        margin-bottom: 8px;
                        background: rgba(255,255,255,0.02);
                        border-radius: 4px;
                    ">
                        <strong>{cat_name}</strong><br>
                        <span style="font-size: 0.85em; color: #888;">
                            {finding_count} finding{'s' if finding_count != 1 else ''}
                        </span>
                    </div>""",
                    unsafe_allow_html=True,
                )

                if sev_summary:
                    parts = []
                    for sev in ["critical", "high", "medium", "low", "insight"]:
                        cnt = sev_summary.get(sev, 0)
                        if cnt > 0:
                            emoji = Severity(sev).emoji
                            parts.append(f"{emoji} {cnt}")
                    st.caption(" | ".join(parts))


def _top_findings(audit):
    """Render the top findings list."""
    top = audit.get_top_findings(10)
    if not top:
        st.info("No critical findings detected.")
        return

    for i, finding in enumerate(top, 1):
        severity = finding.severity
        with st.expander(
            f"{severity.emoji} **{finding.metric_name}** — {finding.summary[:80]}",
            expanded=(i <= 3),
        ):
            st.markdown(f"**Category:** {finding.category}")
            st.markdown(f"**Severity:** {severity.value.title()}")

            if finding.computed_value is not None:
                st.markdown(f"**Value:** {finding.computed_value:.1f}")
            if finding.affected_count > 0:
                st.markdown(f"**Affected items:** {finding.affected_count:,}")
            if finding.opportunity_value:
                st.markdown(f"**Opportunity:** {finding.opportunity_value}")

            st.markdown(f"**Summary:** {finding.summary}")

            if finding.recommendations:
                st.markdown("**Recommendations:**")
                for rec in finding.recommendations:
                    st.markdown(f"- {rec}")

            if finding.trend_direction:
                st.markdown(f"**Trend:** {finding.trend_direction.value.title()}")


def render():
    st.header("Audit Dashboard")

    audit = st.session_state.get("audit_result")
    if not audit:
        st.info("Run an audit from the Configure page to see results here.")
        st.page_link("pages/2_Configure.py", label="Go to Configure", icon="⚙️")
        return

    # --- Health Score Header ---
    score = audit.health_score
    grade = audit.health_grade
    color = _grade_color(grade)

    col_grade, col_score, col_findings, col_metrics = st.columns(4)
    with col_grade:
        st.markdown(
            f"""<div style="
                text-align: center; font-size: 4em; font-weight: bold;
                color: {color}; line-height: 1.1;
            ">{grade}</div>
            <div style="text-align: center; color: #888; font-size: 0.9em;">
                Health Grade
            </div>""",
            unsafe_allow_html=True,
        )
    with col_score:
        st.metric("Health Score", f"{score}/100")
    with col_findings:
        st.metric("Total Findings", audit.total_findings)
    with col_metrics:
        st.metric("Metrics Run", len(audit.metrics_executed))

    st.markdown("---")

    # --- Severity Distribution ---
    st.subheader("Severity Distribution")
    _severity_bar_chart(audit.severity_counts)

    st.markdown("---")

    # --- Category Overview ---
    st.subheader("Category Overview")
    _category_cards(audit.results_by_category)

    st.markdown("---")

    # --- Top Findings ---
    st.subheader("Top Findings")
    _top_findings(audit)

    # --- Audit metadata ---
    with st.expander("Audit Details"):
        st.markdown(f"**Property:** {audit.property_url}")
        st.markdown(f"**Date Range:** {audit.start_date} to {audit.end_date}")
        st.markdown(f"**Metrics Executed:** {len(audit.metrics_executed)}")


render()
