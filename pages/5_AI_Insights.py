"""AI Insights — Executive summary, content plan, group narratives."""

import streamlit as st

from ai.openrouter_client import OpenRouterClient
from ai.insight_generator import InsightGenerator


def _generate_insights(audit):
    """Run AI post-processing to generate insights."""
    client = OpenRouterClient()

    if not client.is_configured:
        st.error(
            "OpenRouter API key not configured. "
            "Add OPENROUTER_API_KEY to your secrets."
        )
        return

    generator = InsightGenerator(client)

    # Group narratives
    with st.spinner("Generating category narratives..."):
        progress_bar = st.progress(0.0)

        def on_narrative_progress(current, total):
            progress_bar.progress(current / total)

        narratives = generator.generate_group_narratives(
            audit=audit,
            progress_callback=on_narrative_progress,
        )
        audit.ai_group_analyses = narratives
        progress_bar.progress(1.0)

    # Executive summary
    with st.spinner("Generating executive summary..."):
        summary = generator.generate_executive_summary(
            audit=audit,
            category_narratives=narratives,
        )
        audit.ai_executive_summary = summary

    # Content plan
    with st.spinner("Generating content plan..."):
        plan = generator.generate_content_plan(audit=audit)
        if plan:
            audit.ai_content_plan = plan

    st.session_state["audit_result"] = audit
    st.success("AI insights generated successfully!")


def _render_content_plan(plan):
    """Render the content optimization plan."""
    if not plan or not isinstance(plan, dict):
        st.info("No content plan available.")
        return

    timeframes = [
        ("this_week", "This Week", "Quick wins"),
        ("this_month", "This Month", "Medium-term"),
        ("this_quarter", "This Quarter", "Strategic"),
    ]

    for key, title, subtitle in timeframes:
        items = plan.get(key, [])
        if not items:
            continue

        st.markdown(f"#### {title}")
        st.caption(subtitle)

        for item in items:
            if isinstance(item, dict):
                action = item.get("action", "")
                target = item.get("target", "")
                impact = item.get("impact", "")
                effort = item.get("effort", "")

                cols = st.columns([3, 1])
                with cols[0]:
                    st.markdown(f"- **{action}**")
                    if target:
                        st.caption(f"Target: {target}")
                with cols[1]:
                    if effort:
                        effort_colors = {
                            "low": "green",
                            "medium": "orange",
                            "high": "red",
                        }
                        color = effort_colors.get(
                            effort.lower(), "gray"
                        )
                        st.markdown(
                            f":{color}[{effort.title()} effort]"
                        )
            elif isinstance(item, str):
                st.markdown(f"- {item}")


def render():
    st.header("AI Insights")

    audit = st.session_state.get("audit_result")
    if not audit:
        st.info(
            "Run an audit from the Configure page "
            "to see AI insights here."
        )
        st.page_link(
            "pages/2_Configure.py",
            label="Go to Configure",
            icon="⚙️",
        )
        return

    # Check if insights have been generated
    has_insights = bool(audit.ai_executive_summary)

    if not has_insights:
        st.info(
            "AI insights have not been generated yet for "
            "this audit run."
        )
        if st.button(
            "Generate AI Insights",
            type="primary",
            use_container_width=True,
        ):
            _generate_insights(audit)
            st.rerun()
        return

    # --- Executive Summary ---
    st.subheader("Executive Summary")
    st.markdown(audit.ai_executive_summary)

    st.markdown("---")

    # --- Content Plan ---
    if audit.ai_content_plan:
        st.subheader("Content Optimization Plan")
        _render_content_plan(audit.ai_content_plan)
        st.markdown("---")

    # --- Priority Matrix ---
    st.subheader("Priority Matrix")
    top = audit.get_top_findings(10)
    if top:
        cols = st.columns(2)
        with cols[0]:
            st.markdown("**Urgent (Critical + High)**")
            urgent = [
                r for r in top
                if r.severity.value in ("critical", "high")
            ]
            for r in urgent:
                st.markdown(
                    f"- {r.severity.emoji} "
                    f"**{r.metric_name}**: {r.summary[:60]}..."
                )
            if not urgent:
                st.caption("No urgent findings")

        with cols[1]:
            st.markdown("**Monitor (Medium + Low)**")
            monitor = [
                r for r in top
                if r.severity.value in ("medium", "low")
            ]
            for r in monitor:
                st.markdown(
                    f"- {r.severity.emoji} "
                    f"**{r.metric_name}**: {r.summary[:60]}..."
                )
            if not monitor:
                st.caption("No monitoring items")

    st.markdown("---")

    # --- Category Narratives ---
    st.subheader("Category Analysis")
    if audit.ai_group_analyses:
        for category, narrative in (
            audit.ai_group_analyses.items()
        ):
            cat_results = audit.results_by_category.get(
                category, []
            )
            count = len(cat_results)
            with st.expander(
                f"{category} ({count} findings)",
                expanded=False,
            ):
                st.markdown(narrative)
    else:
        st.info("No category narratives available.")

    # --- Regenerate button ---
    st.markdown("---")
    if st.button("Regenerate AI Insights"):
        _generate_insights(audit)
        st.rerun()


render()
