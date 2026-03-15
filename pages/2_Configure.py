"""Configure page — Audit settings, URL filters, and metric scope.

The audit pipeline runs synchronously inside the button callback.
st.status() and st.progress() provide real-time feedback during execution.
"""

import logging

import streamlit as st

logger = logging.getLogger(__name__)

from core.data_store import DataStore
from core.data_fetcher import DataFetcher
from models.url_filter_config import (
    URLFilterConfig,
    FILTER_CATEGORIES,
    DEFAULT_EXCLUDE_RULES,
)
from models.data_shapes import (
    METRIC_CATEGORIES,
    get_required_shapes,
    needs_url_inspection,
    needs_ai_preprocessing,
)
from models.audit_result import AuditResult
from utils.date_utils import get_date_range


# ==============================================================
# Helpers
# ==============================================================

def _build_url_filter_config() -> URLFilterConfig:
    """Build URLFilterConfig from current session state."""
    config = URLFilterConfig()

    for rule in config.exclude_rules:
        key = f"filter_cat_{rule.category}"
        if key in st.session_state:
            rule.enabled = st.session_state[key]

    custom_exclude = st.session_state.get("custom_exclude_text", "")
    if custom_exclude.strip():
        config.custom_exclude_patterns = [
            p.strip() for p in custom_exclude.strip().split("\n") if p.strip()
        ]

    custom_include = st.session_state.get("custom_include_text", "")
    if custom_include.strip():
        config.custom_include_patterns = [
            p.strip() for p in custom_include.strip().split("\n") if p.strip()
        ]

    return config


def _get_selected_metric_ids() -> list[int]:
    """Get metric IDs based on scope selection."""
    scope = st.session_state.get("metric_scope", "All 100 Metrics")

    if scope == "All 100 Metrics":
        return list(range(1, 101))

    if scope == "Custom Selection":
        selected = []
        for cat_name, (start, end) in METRIC_CATEGORIES.items():
            key = f"cat_select_{cat_name}"
            if st.session_state.get(key, False):
                selected.extend(range(start, end + 1))
        return selected if selected else list(range(1, 101))

    for cat_name, (start, end) in METRIC_CATEGORIES.items():
        if scope == cat_name:
            return list(range(start, end + 1))

    return list(range(1, 101))


# ==============================================================
# Audit pipeline — runs synchronously with live feedback
# ==============================================================

def _run_audit(
    metric_ids: list[int],
    days: int,
    url_filter_config: URLFilterConfig,
):
    """Run the complete audit pipeline with live st.status() feedback.

    Runs synchronously inside the button callback so the user sees
    real-time progress updates. Shows results directly after completion
    (no st.rerun — results persist in session state for future views).
    """
    import traceback

    site_url = st.session_state["selected_property"]
    client = st.session_state["gsc_client"]
    audit = None

    progress_bar = st.progress(0.0, text="Starting audit...")

    try:
        with st.status("Running audit...", expanded=True) as status:

            # ---- Step 1: Fetch GSC Data Shapes ----
            st.write("**Step 1/4 — Fetching GSC data shapes...**")

            store = DataStore()
            st.session_state["data_store"] = store
            fetcher = DataFetcher(
                client=client, store=store, site_url=site_url
            )

            def on_fetch_progress(current, total, msg):
                pct = current / max(total, 1) * 0.4
                progress_bar.progress(
                    min(pct, 0.4), text=f"Step 1: {msg}"
                )
                st.write(f"  {msg}")

            try:
                fetcher.fetch_for_metrics(
                    metric_ids=metric_ids,
                    progress_callback=on_fetch_progress,
                    url_filter=url_filter_config,
                    skip_url_inspection=True,
                )
                shapes = store.fetched_shapes
                st.write(
                    f"Fetched **{len(shapes)}** data shapes "
                    f"({store.memory_usage_mb:.1f} MB)"
                )
            except Exception as e:
                st.error(f"Data fetch failed: {e}")
                logger.exception("Data fetch failed")
                progress_bar.progress(1.0, text="Audit failed.")
                status.update(label="Audit failed", state="error")
                return

            # ---- Step 2: URL Inspection ----
            if needs_url_inspection(metric_ids):
                st.write("**Step 2/4 — Inspecting URLs...**")

                def on_inspect_progress(current, total, msg):
                    pct = 0.4 + (current / max(total, 1) * 0.4)
                    progress_bar.progress(
                        min(pct, 0.8), text=f"Step 2: {msg}"
                    )

                try:
                    fetcher.fetch_url_inspections(
                        url_filter=url_filter_config,
                        progress_callback=on_inspect_progress,
                    )
                    insp = store.get("url_inspection")
                    count = (
                        len(insp) if isinstance(insp, dict) else 0
                    )
                    st.write(f"Inspected **{count}** URLs")
                except Exception as e:
                    st.warning(
                        f"URL inspection error (non-fatal): {e}"
                    )
                    logger.warning(f"URL inspection: {e}")
            else:
                st.write(
                    "**Step 2/4 — URL inspection not needed, "
                    "skipping.**"
                )

            progress_bar.progress(
                0.8, text="Step 3: Computing metrics..."
            )

            # ---- Step 3: AI + Metric Computation ----
            st.write("**Step 3/4 — Computing metrics...**")
            ai_classifications = st.session_state.get(
                "ai_classifications", {}
            )

            try:
                if not ai_classifications:
                    from core.supabase_client import SupabaseClient

                    sb = SupabaseClient()
                    if sb.is_configured:
                        ai_classifications = (
                            sb.get_cached_classifications(site_url)
                        )
                        if ai_classifications:
                            st.session_state["ai_classifications"] = (
                                ai_classifications
                            )
                            st.write(
                                f"Loaded {len(ai_classifications)} "
                                "cached AI classifications"
                            )

                ai_enabled = st.session_state.get("ai_enabled", True)
                if ai_enabled:
                    from ai.openrouter_client import OpenRouterClient
                    from ai.preprocessor import AIPreprocessor

                    or_client = OpenRouterClient()
                    if or_client.is_configured:
                        st.write("Running AI classifications...")
                        preprocessor = AIPreprocessor(
                            client=or_client,
                            brand_name=st.session_state.get(
                                "brand_name", ""
                            ),
                            cache=ai_classifications,
                        )
                        ai_classifications = preprocessor.process(
                            store=store
                        )
                        st.session_state["ai_classifications"] = (
                            ai_classifications
                        )
                        st.write(
                            f"AI classified "
                            f"{len(ai_classifications)} queries"
                        )
                    else:
                        st.write(
                            "OpenRouter not configured — AI skipped"
                        )
                else:
                    st.write("AI disabled by user")
            except Exception as e:
                st.write(f"AI error (non-fatal): {e}")
                logger.warning(f"AI preprocessing: {e}")

            progress_bar.progress(
                0.85, text="Step 3: Running 100 metrics..."
            )

            results = []
            try:
                from metrics import run_all_metrics

                results = run_all_metrics(
                    metric_ids=metric_ids,
                    store=store,
                    brand_name=st.session_state.get("brand_name", ""),
                    ai_classifications=ai_classifications,
                )
                st.write(
                    f"Computed **{len(results)}** metric results"
                )
                if results:
                    from collections import Counter

                    sev = Counter(
                        r.severity.value for r in results
                    )
                    st.write(
                        "Severity: "
                        + ", ".join(
                            f"{s}={c}" for s, c in sev.items()
                        )
                    )
            except Exception as e:
                st.error(f"Metric computation failed: {e}")
                st.code(traceback.format_exc())
                logger.exception("Metric computation failed")

            # ---- Step 4: Build + Save ----
            progress_bar.progress(
                0.92, text="Step 4: Saving results..."
            )
            st.write("**Step 4/4 — Saving results...**")

            start_date, end_date = get_date_range(days)
            audit = AuditResult(
                property_url=site_url,
                start_date=start_date,
                end_date=end_date,
                metrics_executed=metric_ids,
            )
            audit.add_results(results)
            st.session_state["audit_result"] = audit

            st.write(
                f"Health Score: **{audit.health_score}/100** "
                f"(Grade: **{audit.health_grade}**) — "
                f"{audit.total_findings} findings"
            )

            # Save to Supabase
            try:
                from core.supabase_client import SupabaseClient

                sb = SupabaseClient()
                if sb.is_configured:
                    run_id = sb.save_audit_run(audit)
                    if run_id:
                        st.session_state[
                            "current_audit_run_id"
                        ] = run_id
                        st.write(f"Saved audit run: `{run_id}`")
                    if ai_classifications:
                        sb.save_classifications(
                            site_url, ai_classifications
                        )
                        st.write("Saved AI classifications")
                else:
                    st.write("Supabase not configured — skipped")
            except Exception as e:
                st.write(f"Supabase save error: {e}")

            progress_bar.progress(1.0, text="Audit complete!")
            status.update(
                label=(
                    f"Audit complete! Score: "
                    f"{audit.health_score}/100 "
                    f"({audit.health_grade})"
                ),
                state="complete",
                expanded=True,
            )

    except BaseException as e:
        # Catch ANYTHING — show it on screen so user sees it
        st.error(
            f"PIPELINE CRASH: {type(e).__name__}: {e}"
        )
        st.code(traceback.format_exc())
        logger.exception("Pipeline crash")
        return

    # ---- Show results directly (no st.rerun) ----
    if audit:
        st.success(
            f"### Audit Complete! "
            f"Grade: **{audit.health_grade}** — "
            f"{audit.health_score}/100\n\n"
            f"**{audit.total_findings}** findings across "
            f"**{len(audit.metrics_executed)}** metrics"
        )
        c1, c2 = st.columns(2)
        with c1:
            st.page_link(
                "pages/3_Dashboard.py",
                label="View Dashboard",
                icon="📊",
                use_container_width=True,
            )
        with c2:
            st.page_link(
                "pages/4_Metrics_Explorer.py",
                label="Explore Metrics",
                icon="🔍",
                use_container_width=True,
            )


# ==============================================================
# Main page
# ==============================================================

def render():
    st.header("Configure Audit")

    if not st.session_state.get("authenticated"):
        st.warning("Please connect to Google Search Console first.")
        st.page_link(
            "pages/1_Connect.py", label="Go to Connect page", icon="🔌"
        )
        return

    if not st.session_state.get("selected_property"):
        st.warning("Please select a GSC property first.")
        st.page_link(
            "pages/1_Connect.py", label="Go to Connect page", icon="🔌"
        )
        return

    # ----- RESULTS AT THE TOP (always visible) -----
    audit = st.session_state.get("audit_result")
    if audit:
        st.success(
            f"### Grade: **{audit.health_grade}** — "
            f"{audit.health_score}/100\n\n"
            f"**{audit.total_findings}** findings across "
            f"**{len(audit.metrics_executed)}** metrics  |  "
            f"{audit.start_date} to {audit.end_date}"
        )
        c1, c2 = st.columns(2)
        with c1:
            st.page_link(
                "pages/3_Dashboard.py",
                label="View Dashboard",
                icon="📊",
                use_container_width=True,
            )
        with c2:
            st.page_link(
                "pages/4_Metrics_Explorer.py",
                label="Explore Metrics",
                icon="🔍",
                use_container_width=True,
            )
        st.markdown("---")

    # ----- CONFIG UI -----
    st.info(f"Property: **{st.session_state['selected_property']}**")

    # --- Date Range ---
    st.subheader("Date Range")
    days = st.slider(
        "Analysis window (days):",
        min_value=7,
        max_value=365,
        value=90,
        step=1,
        key="audit_days",
    )
    start_date, end_date = get_date_range(days)
    st.caption(
        f"Analyzing: {start_date} to {end_date} (GSC data has 2-3 day lag)"
    )

    st.markdown("---")

    # --- URL Filters ---
    st.subheader("URL Filters")
    st.caption(
        "Control which URLs are included in the analysis. "
        "Homepage is always included."
    )

    col1, col2 = st.columns(2)
    exclude_categories = {}
    for rule in DEFAULT_EXCLUDE_RULES:
        exclude_categories.setdefault(rule.category, []).append(rule)

    cat_list = list(exclude_categories.keys())
    half = len(cat_list) // 2

    with col1:
        for cat in cat_list[:half + 1]:
            label = FILTER_CATEGORIES.get(cat, cat)
            count = len(exclude_categories[cat])
            st.toggle(
                f"{label} ({count} rules)",
                value=True,
                key=f"filter_cat_{cat}",
            )

    with col2:
        for cat in cat_list[half + 1 :]:
            label = FILTER_CATEGORIES.get(cat, cat)
            count = len(exclude_categories[cat])
            st.toggle(
                f"{label} ({count} rules)",
                value=True,
                key=f"filter_cat_{cat}",
            )

    with st.expander("Custom Patterns"):
        st.text_area(
            "Additional exclude patterns (one per line):",
            key="custom_exclude_text",
            placeholder="/example-path/\n/another-path/",
            height=80,
        )
        st.text_area(
            "Additional include patterns (one per line):",
            key="custom_include_text",
            placeholder="/important-section/",
            height=80,
        )

    st.markdown("---")

    # --- Metric Scope ---
    st.subheader("Metric Scope")
    scope_options = ["All 100 Metrics", "Custom Selection"]
    scope = st.radio(
        "Which metrics to run:",
        scope_options,
        horizontal=True,
        key="metric_scope",
    )

    if scope == "Custom Selection":
        st.caption("Select categories to include:")
        cols = st.columns(3)
        for idx, (cat_name, (start, end)) in enumerate(
            METRIC_CATEGORIES.items()
        ):
            count = end - start + 1
            with cols[idx % 3]:
                st.checkbox(
                    f"{cat_name} ({count})",
                    value=True,
                    key=f"cat_select_{cat_name}",
                )

    metric_ids = _get_selected_metric_ids()
    st.caption(f"**{len(metric_ids)}** metrics selected")

    st.markdown("---")

    # --- AI Analysis ---
    st.subheader("AI Analysis")
    ai_enabled = st.toggle(
        "Enable AI Analysis", value=True, key="ai_enabled"
    )
    if ai_enabled:
        ai_metrics = [m for m in metric_ids if m in {8, 26, 51, 52, 53, 97}]
        st.caption(
            f"AI will classify queries and generate insights. "
            f"{len(ai_metrics)} metrics use AI classifications. "
            f"Estimated cost: ~$1-4 depending on query volume."
        )

    st.markdown("---")

    # --- Audit Summary ---
    required_shapes = get_required_shapes(metric_ids)
    needs_insp = needs_url_inspection(metric_ids)
    needs_ai = needs_ai_preprocessing(metric_ids)

    with st.expander("Audit Summary", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Metrics", len(metric_ids))
        c2.metric("API Shapes", len(required_shapes))
        c3.metric("URL Inspection", "Yes" if needs_insp else "No")
        c4.metric("AI Pre-Processing", "Yes" if needs_ai else "No")

    # --- Run Audit Button ---
    st.markdown("---")

    if st.button("Run Audit", type="primary", use_container_width=True):
        url_filter_config = _build_url_filter_config()
        st.session_state["url_filter_config"] = url_filter_config
        _run_audit(metric_ids, days, url_filter_config)


render()
