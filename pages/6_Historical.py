"""Historical — Trend comparisons from Supabase data."""

import streamlit as st
import plotly.express as px
import pandas as pd

from core.supabase_client import SupabaseClient


def _load_audit_history(property_url: str) -> list[dict]:
    """Load audit history from Supabase."""
    sb = SupabaseClient()
    if not sb.is_configured:
        return []
    return sb.get_audit_history(property_url, limit=50)


def render():
    st.header("Historical Analysis")

    property_url = st.session_state.get("selected_property")
    if not property_url:
        st.info(
            "Connect to a GSC property first to see "
            "historical data."
        )
        st.page_link(
            "pages/1_Connect.py",
            label="Go to Connect",
            icon="🔌",
        )
        return

    # Load Supabase history
    sb = SupabaseClient()
    has_supabase = sb.is_configured

    # --- Current Audit Summary ---
    audit = st.session_state.get("audit_result")
    if audit:
        st.subheader("Current Audit Snapshot")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Health Score", f"{audit.health_score}/100")
        with col2:
            st.metric("Grade", audit.health_grade)
        with col3:
            st.metric("Findings", audit.total_findings)
        st.markdown("---")

    # --- Historical Data from Supabase ---
    if has_supabase:
        history = _load_audit_history(property_url)

        if history:
            st.subheader("Audit Run History")

            # Health score trend chart
            trend_data = []
            for run in history:
                trend_data.append({
                    "Date": run.get(
                        "created_at", ""
                    )[:10],
                    "Health Score": run.get(
                        "health_score", 0
                    ),
                    "Grade": run.get("health_grade", "?"),
                    "Findings": run.get(
                        "total_findings", 0
                    ),
                })

            if trend_data:
                df = pd.DataFrame(trend_data)
                fig = px.line(
                    df,
                    x="Date",
                    y="Health Score",
                    markers=True,
                    title="Health Score Trend",
                )
                fig.update_layout(
                    yaxis_range=[0, 100],
                    height=350,
                    margin=dict(t=40, b=20),
                )
                st.plotly_chart(
                    fig, use_container_width=True
                )

            # History table
            st.dataframe(
                pd.DataFrame(trend_data),
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("---")

            # Run comparison
            st.subheader("Compare Audit Runs")
            if len(history) >= 2:
                run_options = {
                    f"{r.get('created_at', '')[:10]} "
                    f"(Score: {r.get('health_score', '?')})": r
                    for r in history
                }

                col1, col2 = st.columns(2)
                with col1:
                    run_a_label = st.selectbox(
                        "Run A",
                        list(run_options.keys()),
                        index=0,
                        key="hist_run_a",
                    )
                with col2:
                    run_b_label = st.selectbox(
                        "Run B",
                        list(run_options.keys()),
                        index=min(
                            1, len(run_options) - 1
                        ),
                        key="hist_run_b",
                    )

                if run_a_label and run_b_label:
                    run_a = run_options[run_a_label]
                    run_b = run_options[run_b_label]

                    comp_data = {
                        "Metric": [
                            "Health Score",
                            "Grade",
                            "Total Findings",
                        ],
                        "Run A": [
                            run_a.get("health_score", 0),
                            run_a.get("health_grade", "?"),
                            run_a.get("total_findings", 0),
                        ],
                        "Run B": [
                            run_b.get("health_score", 0),
                            run_b.get("health_grade", "?"),
                            run_b.get("total_findings", 0),
                        ],
                    }

                    # Add severity comparisons
                    sev_a = run_a.get(
                        "severity_counts", {}
                    )
                    sev_b = run_b.get(
                        "severity_counts", {}
                    )
                    for sev in [
                        "critical", "high",
                        "medium", "low",
                    ]:
                        comp_data["Metric"].append(
                            f"{sev.title()} Findings"
                        )
                        comp_data["Run A"].append(
                            sev_a.get(sev, 0)
                        )
                        comp_data["Run B"].append(
                            sev_b.get(sev, 0)
                        )

                    st.dataframe(
                        pd.DataFrame(comp_data),
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                st.caption(
                    "Run at least 2 audits to compare."
                )

        else:
            st.info(
                "No audit history found for this property. "
                "Run an audit to start tracking."
            )
    else:
        st.warning(
            "Supabase is not configured. Add "
            "SUPABASE_URL and SUPABASE_ANON_KEY to "
            "your secrets to enable historical tracking."
        )

        # Show current session data only
        if audit:
            st.subheader("Severity Distribution")
            sev_data = []
            for sev, count in (
                audit.severity_counts.items()
            ):
                if count > 0:
                    sev_data.append({
                        "Severity": sev.title(),
                        "Count": count,
                    })

            if sev_data:
                fig = px.pie(
                    pd.DataFrame(sev_data),
                    values="Count",
                    names="Severity",
                    color="Severity",
                    color_discrete_map={
                        "Critical": "#DC3545",
                        "High": "#FD7E14",
                        "Medium": "#FFC107",
                        "Low": "#0D6EFD",
                        "Insight": "#6C757D",
                    },
                )
                fig.update_layout(
                    height=300,
                    margin=dict(t=10, b=10),
                )
                st.plotly_chart(
                    fig, use_container_width=True
                )


render()
