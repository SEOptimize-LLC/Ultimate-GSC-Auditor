"""Configure page — Audit settings, URL filters, and metric scope."""

import logging

import streamlit as st

logger = logging.getLogger(__name__)

from core.data_store import DataStore
from core.data_fetcher import DataFetcher
from core.url_filter import URLFilter
from models.url_filter_config import (
    URLFilterConfig,
    FILTER_CATEGORIES,
    DEFAULT_EXCLUDE_RULES,
    DEFAULT_INCLUDE_RULES,
)
from models.data_shapes import (
    METRIC_CATEGORIES,
    METRIC_NAMES,
    get_required_shapes,
    needs_url_inspection,
    needs_sitemaps,
    needs_ai_preprocessing,
)
from models.audit_result import AuditResult
from utils.date_utils import get_date_range


def _build_url_filter_config() -> URLFilterConfig:
    """Build URLFilterConfig from current session state."""
    config = URLFilterConfig()

    # Apply category toggles
    for rule in config.exclude_rules:
        key = f"filter_cat_{rule.category}"
        if key in st.session_state:
            rule.enabled = st.session_state[key]

    # Apply custom patterns
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

    # By category name
    for cat_name, (start, end) in METRIC_CATEGORIES.items():
        if scope == cat_name:
            return list(range(start, end + 1))

    return list(range(1, 101))


def _run_audit_pipeline(metric_ids: list[int], days: int):
    """Execute the audit pipeline: fetch -> compute -> store."""
    progress_bar = st.progress(0.0)
    status_text = st.empty()

    # Phase 1: Fetch data
    status_text.text("Fetching GSC data...")
    store = DataStore()
    st.session_state["data_store"] = store

    client = st.session_state["gsc_client"]
    site_url = st.session_state["selected_property"]

    url_filter_config = _build_url_filter_config()
    st.session_state["url_filter_config"] = url_filter_config
    url_filter = URLFilter(url_filter_config)

    fetcher = DataFetcher(client=client, store=store, site_url=site_url)

    required_shapes = get_required_shapes(metric_ids)
    total_steps = len(required_shapes) + 2  # +1 compute, +1 finalize

    def on_fetch_progress(current, total, msg):
        pct = current / total_steps
        progress_bar.progress(min(pct, 0.8))
        status_text.text(msg)

    fetcher.fetch_for_metrics(
        metric_ids=metric_ids,
        progress_callback=on_fetch_progress,
        url_filter=url_filter_config,
    )

    # Phase 2: AI pre-processing (if enabled)
    # Load cached classifications from Supabase
    ai_classifications = st.session_state.get(
        "ai_classifications", {}
    )
    if not ai_classifications:
        try:
            from core.supabase_client import SupabaseClient
            sb = SupabaseClient()
            if sb.is_configured:
                ai_classifications = (
                    sb.get_cached_classifications(site_url)
                )
                if ai_classifications:
                    st.session_state[
                        "ai_classifications"
                    ] = ai_classifications
                    status_text.text(
                        f"Loaded {len(ai_classifications)} "
                        f"cached classifications"
                    )
        except Exception:
            pass

    ai_enabled = st.session_state.get("ai_enabled", True)

    if ai_enabled:
        status_text.text("Running AI classifications...")
        progress_bar.progress(0.82)

        try:
            from ai.openrouter_client import OpenRouterClient
            from ai.preprocessor import AIPreprocessor

            or_client = OpenRouterClient()
            if or_client.is_configured:
                preprocessor = AIPreprocessor(
                    client=or_client,
                    brand_name=st.session_state.get(
                        "brand_name", ""
                    ),
                    cache=ai_classifications,
                )
                ai_classifications = preprocessor.process(
                    store=store,
                )
                st.session_state[
                    "ai_classifications"
                ] = ai_classifications
        except Exception as e:
            status_text.text(f"AI pre-processing skipped: {e}")

    # Phase 3: Compute metrics
    status_text.text("Computing metrics...")
    progress_bar.progress(0.88)

    from metrics import run_all_metrics

    results = run_all_metrics(
        metric_ids=metric_ids,
        store=store,
        brand_name=st.session_state.get("brand_name", ""),
        ai_classifications=ai_classifications,
    )

    # Phase 4: Build audit result
    status_text.text("Building audit report...")
    progress_bar.progress(0.95)

    start_date, end_date = get_date_range(days)
    audit = AuditResult(
        property_url=site_url,
        start_date=start_date,
        end_date=end_date,
        metrics_executed=metric_ids,
    )
    audit.add_results(results)

    st.session_state["audit_result"] = audit
    st.session_state["audit_running"] = False

    # Phase 5: Save to Supabase (non-blocking)
    try:
        from core.supabase_client import SupabaseClient

        sb = SupabaseClient()
        if sb.is_configured:
            status_text.text("Saving to Supabase...")
            run_id = sb.save_audit_run(audit)
            if run_id:
                st.session_state[
                    "current_audit_run_id"
                ] = run_id
            # Cache AI classifications
            if ai_classifications:
                sb.save_classifications(
                    site_url, ai_classifications
                )
    except Exception as e:
        logger.warning(f"Supabase save skipped: {e}")

    progress_bar.progress(1.0)
    status_text.text(
        f"Audit complete! Health Score: "
        f"{audit.health_score}/100 "
        f"(Grade: {audit.health_grade})"
    )


def render():
    st.header("Configure Audit")

    if not st.session_state.get("authenticated"):
        st.warning("Please connect to Google Search Console first.")
        st.page_link("pages/1_Connect.py", label="Go to Connect page", icon="🔌")
        return

    if not st.session_state.get("selected_property"):
        st.warning("Please select a GSC property first.")
        st.page_link("pages/1_Connect.py", label="Go to Connect page", icon="🔌")
        return

    st.info(f"Configuring audit for: **{st.session_state['selected_property']}**")

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
    st.caption(f"Analyzing: {start_date} to {end_date} (GSC data has 2-3 day lag)")

    st.markdown("---")

    # --- URL Filters ---
    st.subheader("URL Filters")
    st.caption(
        "Control which URLs are included in the analysis. "
        "Homepage is always included."
    )

    # Category toggles
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
        for cat in cat_list[half + 1:]:
            label = FILTER_CATEGORIES.get(cat, cat)
            count = len(exclude_categories[cat])
            st.toggle(
                f"{label} ({count} rules)",
                value=True,
                key=f"filter_cat_{cat}",
            )

    # Custom patterns
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
        for idx, (cat_name, (start, end)) in enumerate(METRIC_CATEGORIES.items()):
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
    ai_enabled = st.toggle("Enable AI Analysis", value=True, key="ai_enabled")
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
    needs_sm = needs_sitemaps(metric_ids)
    needs_ai = needs_ai_preprocessing(metric_ids)

    with st.expander("Audit Summary", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Metrics", len(metric_ids))
        c2.metric("API Shapes", len(required_shapes))
        c3.metric("URL Inspection", "Yes" if needs_insp else "No")
        c4.metric("AI Pre-Processing", "Yes" if needs_ai else "No")

    # --- Run Button ---
    st.markdown("---")

    already_running = st.session_state.get("audit_running", False)

    if st.button(
        "Run Audit",
        type="primary",
        use_container_width=True,
        disabled=already_running,
    ):
        st.session_state["audit_running"] = True
        try:
            _run_audit_pipeline(metric_ids, days)
            st.balloons()
            st.switch_page("pages/3_Dashboard.py")
        except Exception as e:
            st.session_state["audit_running"] = False
            st.error(f"Audit failed: {e}")
            logger.exception("Audit pipeline error")

    # Show previous result summary if exists
    audit = st.session_state.get("audit_result")
    if audit and not already_running:
        st.success(
            f"Last audit: **{audit.health_grade}** "
            f"({audit.health_score}/100) — "
            f"{audit.total_findings} findings"
        )
        st.page_link(
            "pages/3_Dashboard.py",
            label="View Dashboard",
            icon="📊",
        )


render()
