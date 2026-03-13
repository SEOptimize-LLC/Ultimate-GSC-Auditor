"""Metrics Explorer — Deep-dive into individual metrics."""

import streamlit as st
import pandas as pd

from models.metric_result import Severity, TrendDirection
from models.data_shapes import METRIC_CATEGORIES


def _render_metric_detail(result):
    """Render the full detail view for a single metric result."""
    severity = result.severity

    # Header with severity badge
    st.markdown(
        f"### {severity.emoji} {result.metric_name}"
    )

    # Key metrics row
    cols = st.columns(4)
    with cols[0]:
        st.metric("Severity", severity.value.title())
    with cols[1]:
        if result.computed_value is not None:
            st.metric("Computed Value", f"{result.computed_value:.2f}")
        else:
            st.metric("Computed Value", "N/A")
    with cols[2]:
        st.metric("Affected Items", f"{result.affected_count:,}")
    with cols[3]:
        if result.trend_direction:
            trend_icons = {
                TrendDirection.IMPROVING: "Improving",
                TrendDirection.DECLINING: "Declining",
                TrendDirection.STABLE: "Stable",
                TrendDirection.NEW: "New",
            }
            st.metric("Trend", trend_icons.get(result.trend_direction, "—"))
        else:
            st.metric("Trend", "—")

    st.markdown("---")

    # Summary
    st.markdown(f"**Summary:** {result.summary}")

    if result.opportunity_value:
        st.info(f"**Opportunity:** {result.opportunity_value}")

    if result.benchmark_comparison:
        st.caption(f"**Benchmark:** {result.benchmark_comparison}")

    # Recommendations
    if result.recommendations:
        st.markdown("#### Recommendations")
        for rec in result.recommendations:
            st.markdown(f"- {rec}")

    # Data table
    if result.data_table is not None and not result.data_table.empty:
        st.markdown("#### Data Table")
        display_df = result.data_table.head(25)

        # Format numeric columns
        for col in display_df.columns:
            if display_df[col].dtype in ["float64", "float32"]:
                display_df[col] = display_df[col].round(2)

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
        )

        if len(result.data_table) > 25:
            st.caption(
                f"Showing top 25 of {len(result.data_table):,} rows"
            )

    # Additional details
    if result.details:
        with st.expander("Raw Details"):
            st.json(result.details)


def render():
    st.header("Metrics Explorer")

    audit = st.session_state.get("audit_result")
    if not audit:
        st.info("Run an audit from the Configure page to see metrics here.")
        st.page_link("pages/2_Configure.py", label="Go to Configure", icon="⚙️")
        return

    # --- Filters ---
    filter_col1, filter_col2 = st.columns(2)

    with filter_col1:
        category_filter = st.selectbox(
            "Category",
            ["All Categories"] + list(METRIC_CATEGORIES.keys()),
            key="explorer_category",
        )

    with filter_col2:
        severity_filter = st.selectbox(
            "Minimum Severity",
            ["All", "Critical", "High", "Medium", "Low"],
            key="explorer_severity",
        )

    # Filter results
    filtered_results = audit.results
    if category_filter != "All Categories":
        filtered_results = [
            r for r in filtered_results if r.category == category_filter
        ]

    if severity_filter != "All":
        sev_pri = Severity(severity_filter.lower()).priority
        filtered_results = [
            r for r in filtered_results
            if r.severity.priority <= sev_pri
        ]

    # Sort by severity (most severe first), then by metric ID
    filtered_results.sort(key=lambda r: (r.severity.priority, r.metric_id))

    st.caption(f"Showing {len(filtered_results)} of {len(audit.results)} findings")

    if not filtered_results:
        st.info("No findings match the selected filters.")
        return

    # --- Metric selector ---
    metric_options = {
        f"{r.severity.emoji} [{r.metric_id}] "
        f"{r.metric_name}": r
        for r in filtered_results
    }

    selected_label = st.selectbox(
        "Select a metric to explore:",
        list(metric_options.keys()),
        key="explorer_metric_select",
    )

    if selected_label:
        selected_result = metric_options[selected_label]
        st.markdown("---")
        _render_metric_detail(selected_result)

    # --- Quick summary table ---
    with st.expander("All Findings Summary"):
        summary_data = []
        for r in filtered_results:
            summary_data.append({
                "ID": r.metric_id,
                "Metric": r.metric_name,
                "Category": r.category,
                "Severity": r.severity.value.title(),
                "Value": (
                    f"{r.computed_value:.2f}"
                    if r.computed_value is not None
                    else "—"
                ),
                "Affected": r.affected_count,
            })

        if summary_data:
            st.dataframe(
                pd.DataFrame(summary_data),
                use_container_width=True,
                hide_index=True,
            )


render()
