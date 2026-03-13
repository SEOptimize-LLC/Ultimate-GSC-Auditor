"""Connect page — OAuth authentication and property selection."""

import streamlit as st

from core.gsc_client import get_authorization_url


def render():
    st.header("Connect to Google Search Console")

    if not st.session_state.get("authenticated"):
        st.markdown(
            "Connect your Google account to access Search Console data. "
            "This grants **read-only** access to your GSC properties."
        )

        col1, col2 = st.columns([1, 2])
        with col1:
            auth_url = get_authorization_url()
            st.link_button(
                "Sign in with Google",
                auth_url,
                type="primary",
                use_container_width=True,
            )

        with col2:
            st.info(
                "You'll be redirected to Google to authorize access. "
                "After signing in, you'll be returned here automatically."
            )

        st.markdown("---")
        st.subheader("What this app analyzes")
        st.markdown("""
This tool computes **100+ custom SEO metrics** from your Google Search Console data, organized into 13 categories:

| Category | Metrics | Focus |
|----------|---------|-------|
| Query Performance | 1-12 | Query footprint depth and quality |
| Click & CTR | 13-21 | How well impressions convert to clicks |
| Impression & Visibility | 22-27 | Visibility trends across content |
| Position & Ranking | 28-34 | Ranking movement and stability |
| Crawl & Index Health | 35-44 | Google's ability to crawl and index |
| Content Health & Decay | 45-48 | Content degradation over time |
| Device & Segment | 49-50 | Mobile vs desktop performance |
| Query Intent & Topical | 51-60 | Query quality and intent alignment |
| Click Behavior | 61-68 | Nuanced click interaction patterns |
| Impression Quality | 69-77 | Meaningful vs noise visibility |
| Ranking Velocity | 78-84 | Speed and trajectory of ranking changes |
| Indexation Coverage | 85-94 | Index health and coverage issues |
| Content Portfolio | 95-100 | Site-wide content library health |
        """)
        return

    # --- Authenticated State ---
    st.success("Connected to Google Search Console")

    # Property Selection
    st.subheader("Select Property")
    properties = st.session_state.get("properties", [])
    if not properties:
        st.warning("No GSC properties found for this account.")
        return

    property_options = [p["url"] for p in properties]
    selected = st.selectbox(
        "GSC Property:",
        options=property_options,
        index=0,
        help="Select the website you want to audit.",
    )
    st.session_state["selected_property"] = selected

    # Property info
    selected_info = next(
        (p for p in properties if p["url"] == selected), {}
    )
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Property URL", selected)
    with col2:
        st.metric("Permission Level", selected_info.get("permission", "N/A"))

    st.markdown("---")

    # Brand Name
    st.subheader("Brand Configuration")
    brand_name = st.text_input(
        "Brand Name:",
        value=st.session_state.get("brand_name", ""),
        help="Enter your brand name for branded vs non-branded query classification. "
             "AI will detect misspellings and abbreviations automatically.",
        placeholder="e.g., Nike, HubSpot, Acme Corp",
    )
    st.session_state["brand_name"] = brand_name

    if brand_name:
        st.caption(
            f"AI will classify queries containing '{brand_name}' "
            f"(and variations) as branded."
        )
    else:
        st.caption(
            "No brand name set. Branded query analysis will be skipped."
        )

    st.markdown("---")

    # Connection status summary
    st.subheader("Connection Status")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Google Auth", "Connected")
    with col2:
        st.metric("Properties Available", len(properties))
    with col3:
        st.metric("Selected Property", selected.split("//")[-1].rstrip("/"))

    st.info("Head to the **Configure** page to set up your audit parameters.")

    # Disconnect option
    with st.expander("Account Options"):
        if st.button("Disconnect Google Account", type="secondary"):
            for key in ["authenticated", "credentials", "gsc_client", "properties",
                       "selected_property", "data_store", "audit_result"]:
                st.session_state[key] = None if key != "authenticated" else False
                if key == "properties":
                    st.session_state[key] = []
            st.rerun()


render()
