"""Configure page — Audit settings, URL filters, and metric scope.

Pipeline runs in three separate phases (via st.rerun) to stay
within Streamlit Cloud's ~30-minute infrastructure timeout:

  Phase 1 (fetch):   Fetch GSC data shapes          (~3 min)
  Phase 2 (inspect): URL inspection batch            (~5-15 min)
  Phase 3 (compute): AI + metrics + save to Supabase (~3 min)
"""

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

PIPELINE_KEY = "_audit_pipeline"


# ==============================================================
# Config helpers
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


def _get_pipeline() -> dict | None:
    """Get the current pipeline state, or None."""
    return st.session_state.get(PIPELINE_KEY)


def _set_pipeline(phase: str, **extra) -> None:
    """Update pipeline state and rerun."""
    p = st.session_state.get(PIPELINE_KEY, {})
    p["phase"] = phase
    p.update(extra)
    st.session_state[PIPELINE_KEY] = p
    st.rerun()


def _clear_pipeline() -> None:
    """Remove pipeline state."""
    st.session_state.pop(PIPELINE_KEY, None)


# ==============================================================
# Pipeline phases — each runs in its own Streamlit script pass
# ==============================================================

def _phase_fetch(pipeline: dict) -> None:
    """Phase 1: Fetch GSC data shapes (no URL inspection)."""
    metric_ids = pipeline["metric_ids"]
    url_filter_config = pipeline["url_filter_config"]

    st.subheader("Phase 1/3 — Fetching GSC Data")
    progress = st.progress(0.0)
    status = st.empty()
    log = st.expander("Fetch Log", expanded=True)

    store = DataStore()
    st.session_state["data_store"] = store

    client = st.session_state["gsc_client"]
    site_url = st.session_state["selected_property"]
    fetcher = DataFetcher(client=client, store=store, site_url=site_url)

    required = get_required_shapes(metric_ids)

    def on_progress(current, total, msg):
        progress.progress(min(current / max(total, 1), 1.0))
        status.text(msg)

    try:
        fetcher.fetch_for_metrics(
            metric_ids=metric_ids,
            progress_callback=on_progress,
            url_filter=url_filter_config,
            skip_url_inspection=True,
        )
    except Exception as e:
        log.write(f"**ERROR:** {e}")
        logger.exception("Phase 1 fetch failed")
        pipeline.setdefault("errors", []).append(f"Fetch: {e}")

    shapes = store.fetched_shapes
    log.write(f"Fetched **{len(shapes)}** shapes ({store.memory_usage_mb:.1f} MB)")
    for s in shapes:
        df = store.get_df(s)
        if hasattr(df, "__len__"):
            log.write(f"  - `{s}`: {len(df):,} rows")

    progress.progress(1.0)
    status.text("Phase 1 complete — advancing to URL inspection...")

    _set_pipeline("inspect")


def _phase_inspect(pipeline: dict) -> None:
    """Phase 2: URL inspection (the slow part, gets its own phase)."""
    metric_ids = pipeline["metric_ids"]
    url_filter_config = pipeline["url_filter_config"]

    # Skip if no metrics need URL inspection
    if not needs_url_inspection(metric_ids):
        st.info("No metrics require URL inspection — skipping.")
        _set_pipeline("compute")
        return

    st.subheader("Phase 2/3 — Inspecting URLs")
    progress = st.progress(0.0)
    status = st.empty()

    store = DataStore()  # accesses existing session state store
    client = st.session_state["gsc_client"]
    site_url = st.session_state["selected_property"]
    fetcher = DataFetcher(client=client, store=store, site_url=site_url)

    def on_url_progress(current, total, msg):
        progress.progress(min(current / max(total, 1), 1.0))
        status.text(f"Phase 2/3: {msg}")

    try:
        fetcher.fetch_url_inspections(
            url_filter=url_filter_config,
            progress_callback=on_url_progress,
        )
    except Exception as e:
        status.text(f"URL inspection error: {e}")
        logger.exception("Phase 2 inspection failed")
        pipeline.setdefault("errors", []).append(f"Inspect: {e}")

    progress.progress(1.0)
    status.text("Phase 2 complete — advancing to metric computation...")

    _set_pipeline("compute")


def _phase_compute(pipeline: dict) -> None:
    """Phase 3: AI pre-processing + metric computation + Supabase save."""
    metric_ids = pipeline["metric_ids"]
    days = pipeline["days"]
    errors = pipeline.get("errors", [])

    st.subheader("Phase 3/3 — Computing Metrics")
    progress = st.progress(0.0)
    status = st.empty()
    log = st.expander("Computation Log", expanded=True)

    store = DataStore()
    client = st.session_state["gsc_client"]
    site_url = st.session_state["selected_property"]

    # --- AI pre-processing ---
    status.text("Loading AI classifications...")
    progress.progress(0.1)
    ai_classifications = st.session_state.get("ai_classifications", {})

    try:
        if not ai_classifications:
            from core.supabase_client import SupabaseClient
            sb = SupabaseClient()
            if sb.is_configured:
                ai_classifications = sb.get_cached_classifications(site_url)
                if ai_classifications:
                    st.session_state["ai_classifications"] = ai_classifications
                    log.write(f"Loaded {len(ai_classifications)} cached classifications")

        ai_enabled = st.session_state.get("ai_enabled", True)
        if ai_enabled:
            from ai.openrouter_client import OpenRouterClient
            from ai.preprocessor import AIPreprocessor

            or_client = OpenRouterClient()
            if or_client.is_configured:
                status.text("Running AI classifications...")
                progress.progress(0.2)
                preprocessor = AIPreprocessor(
                    client=or_client,
                    brand_name=st.session_state.get("brand_name", ""),
                    cache=ai_classifications,
                )
                ai_classifications = preprocessor.process(store=store)
                st.session_state["ai_classifications"] = ai_classifications
                log.write(f"AI classified {len(ai_classifications)} queries")
            else:
                log.write("OpenRouter not configured — AI skipped")
        else:
            log.write("AI disabled by user")
    except Exception as e:
        log.write(f"AI error (non-fatal): {e}")
        logger.warning(f"AI preprocessing: {e}")

    # --- Compute metrics ---
    status.text("Computing 100 metrics...")
    progress.progress(0.5)
    results = []

    try:
        from metrics import run_all_metrics

        results = run_all_metrics(
            metric_ids=metric_ids,
            store=store,
            brand_name=st.session_state.get("brand_name", ""),
            ai_classifications=ai_classifications,
        )
        log.write(f"Computed **{len(results)}** metric results")
        if results:
            from collections import Counter
            sev = Counter(r.severity.value for r in results)
            log.write("  " + ", ".join(f"{s}={c}" for s, c in sev.items()))
        else:
            log.write("**WARNING: No metric results produced!**")
    except Exception as e:
        msg = f"Metric computation FAILED: {e}"
        log.write(f"**ERROR** — {msg}")
        errors.append(msg)
        logger.exception(msg)

    # --- Build audit result ---
    status.text("Building audit report...")
    progress.progress(0.85)

    start_date, end_date = get_date_range(days)
    audit = AuditResult(
        property_url=site_url,
        start_date=start_date,
        end_date=end_date,
        metrics_executed=metric_ids,
    )
    audit.add_results(results)
    st.session_state["audit_result"] = audit

    log.write(
        f"Health Score: **{audit.health_score}/100** "
        f"(Grade: **{audit.health_grade}**) — "
        f"{audit.total_findings} findings"
    )

    # --- Save to Supabase ---
    status.text("Saving to Supabase...")
    progress.progress(0.95)
    try:
        from core.supabase_client import SupabaseClient
        sb = SupabaseClient()
        if sb.is_configured:
            run_id = sb.save_audit_run(audit)
            if run_id:
                st.session_state["current_audit_run_id"] = run_id
                log.write(f"Saved audit run: `{run_id}`")
            if ai_classifications:
                sb.save_classifications(site_url, ai_classifications)
                log.write("Saved AI classifications")
        else:
            log.write("Supabase not configured — skipped")
    except Exception as e:
        log.write(f"Supabase save error: {e}")

    progress.progress(1.0)
    status.text(
        f"Done! Score: {audit.health_score}/100 ({audit.health_grade})"
    )

    # Clear pipeline state and rerun to show results at top
    _clear_pipeline()
    st.rerun()


# ==============================================================
# Phase router
# ==============================================================

def _run_current_phase() -> bool:
    """Run the current pipeline phase. Returns True if a phase ran."""
    pipeline = _get_pipeline()
    if not pipeline:
        return False

    phase = pipeline.get("phase")
    st.info(
        f"Audit in progress for: **{st.session_state.get('selected_property', '?')}**"
    )

    if st.button("Cancel Audit", type="secondary"):
        _clear_pipeline()
        st.rerun()

    if phase == "fetch":
        _phase_fetch(pipeline)
    elif phase == "inspect":
        _phase_inspect(pipeline)
    elif phase == "compute":
        _phase_compute(pipeline)
    else:
        _clear_pipeline()
        st.rerun()

    return True


# ==============================================================
# Main page
# ==============================================================

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

    # ----- PIPELINE IN PROGRESS -----
    if _run_current_phase():
        return  # Phase is running, don't show config UI

    # ----- NORMAL CONFIG UI -----
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
    st.caption(f"Analyzing: {start_date} to {end_date} (GSC data has 2-3 day lag)")

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
        for cat in cat_list[half + 1:]:
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
    needs_ai = needs_ai_preprocessing(metric_ids)

    with st.expander("Audit Summary", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Metrics", len(metric_ids))
        c2.metric("API Shapes", len(required_shapes))
        c3.metric("URL Inspection", "Yes" if needs_insp else "No")
        c4.metric("AI Pre-Processing", "Yes" if needs_ai else "No")

    # --- Run Button ---
    st.markdown("---")

    if st.button(
        "Run Audit",
        type="primary",
        use_container_width=True,
    ):
        url_filter_config = _build_url_filter_config()
        st.session_state["url_filter_config"] = url_filter_config
        st.session_state[PIPELINE_KEY] = {
            "phase": "fetch",
            "metric_ids": metric_ids,
            "days": days,
            "url_filter_config": url_filter_config,
            "errors": [],
        }
        st.rerun()


render()
