"""Ultimate GSC Auditor — Streamlit Application Entry Point."""

import streamlit as st

st.set_page_config(
    page_title="Ultimate GSC Auditor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def init_session_state():
    """Initialize all session state variables."""
    defaults = {
        "authenticated": False,
        "credentials": None,
        "gsc_client": None,
        "properties": [],
        "selected_property": None,
        "brand_name": "",
        "audit_result": None,
        "audit_running": False,
        "audit_progress": 0.0,
        "data_store": None,
        "url_filter_config": None,
        "ai_classifications": {},
        "current_audit_run_id": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def handle_oauth_redirect():
    """Check URL query params for OAuth callback code."""
    auth_code = st.query_params.get("code")
    if auth_code and not st.session_state.get("authenticated"):
        try:
            from core.gsc_client import handle_oauth_callback, GSCClient

            credentials = handle_oauth_callback(auth_code)
            st.session_state["credentials"] = credentials
            st.session_state["gsc_client"] = GSCClient(credentials)
            st.session_state["authenticated"] = True
            st.session_state["properties"] = st.session_state[
                "gsc_client"
            ].list_properties()
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.query_params.clear()
            st.error(f"Authentication failed: {e}")


def main():
    """Main application entry point."""
    init_session_state()
    handle_oauth_redirect()

    # Define pages
    connect_page = st.Page("pages/1_Connect.py", title="Connect", icon="🔌")
    configure_page = st.Page("pages/2_Configure.py", title="Configure", icon="⚙️")
    dashboard_page = st.Page("pages/3_Dashboard.py", title="Dashboard", icon="📊")
    explorer_page = st.Page("pages/4_Metrics_Explorer.py", title="Metrics Explorer", icon="🔍")
    insights_page = st.Page("pages/5_AI_Insights.py", title="AI Insights", icon="🧠")
    historical_page = st.Page("pages/6_Historical.py", title="Historical", icon="📈")
    export_page = st.Page("pages/7_Export.py", title="Export", icon="📥")

    # Navigation
    pg = st.navigation(
        {
            "Setup": [connect_page, configure_page],
            "Analysis": [dashboard_page, explorer_page, insights_page],
            "Data": [historical_page, export_page],
        }
    )
    pg.run()


if __name__ == "__main__":
    main()
