"""Export — Reports in Markdown, HTML, Excel formats."""

import streamlit as st

from reports.markdown_report import generate_markdown_report
from reports.html_report import generate_html_report
from reports.excel_export import generate_excel_report


def render():
    st.header("Export Reports")

    audit = st.session_state.get("audit_result")
    if not audit:
        st.info(
            "Run an audit from the Configure page "
            "to export results."
        )
        st.page_link(
            "pages/2_Configure.py",
            label="Go to Configure",
            icon="⚙️",
        )
        return

    st.info(
        f"Audit: **{audit.property_url}** | "
        f"Grade: **{audit.health_grade}** | "
        f"Score: **{audit.health_score}/100** | "
        f"Findings: **{audit.total_findings}**"
    )

    st.markdown("---")

    # --- Markdown Report ---
    st.subheader("Markdown Report")
    st.caption(
        "Full audit report in Markdown format. "
        "Great for documentation and wikis."
    )

    if st.button("Generate Markdown", key="gen_md"):
        with st.spinner("Generating..."):
            md_content = generate_markdown_report(audit)
            st.session_state["_md_report"] = md_content

    md_report = st.session_state.get("_md_report")
    if md_report:
        st.download_button(
            label="Download Markdown (.md)",
            data=md_report,
            file_name="gsc-audit-report.md",
            mime="text/markdown",
        )
        with st.expander("Preview"):
            st.markdown(md_report)

    st.markdown("---")

    # --- HTML Report ---
    st.subheader("HTML Report")
    st.caption(
        "Styled HTML report that can be opened in any "
        "browser or shared via email."
    )

    if st.button("Generate HTML", key="gen_html"):
        with st.spinner("Generating..."):
            html_content = generate_html_report(audit)
            st.session_state["_html_report"] = html_content

    html_report = st.session_state.get("_html_report")
    if html_report:
        st.download_button(
            label="Download HTML (.html)",
            data=html_report,
            file_name="gsc-audit-report.html",
            mime="text/html",
        )

    st.markdown("---")

    # --- Excel Report ---
    st.subheader("Excel Workbook")
    st.caption(
        "Multi-sheet Excel file with summary, findings, "
        "and data tables per category."
    )

    if st.button("Generate Excel", key="gen_xlsx"):
        with st.spinner("Generating..."):
            xlsx_bytes = generate_excel_report(audit)
            st.session_state["_xlsx_report"] = xlsx_bytes

    xlsx_report = st.session_state.get("_xlsx_report")
    if xlsx_report:
        st.download_button(
            label="Download Excel (.xlsx)",
            data=xlsx_report,
            file_name="gsc-audit-report.xlsx",
            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
        )

    st.markdown("---")

    # --- Raw CSV Data ---
    st.subheader("Raw Data Export")
    st.caption("Export raw GSC data from the current session.")

    store_key = "_gsc_data_store"
    store_data = st.session_state.get(store_key, {})

    if store_data:
        available_shapes = [
            k for k, v in store_data.items()
            if hasattr(v, "to_csv") and not v.empty
        ]

        if available_shapes:
            selected_shape = st.selectbox(
                "Select data shape to export:",
                available_shapes,
                key="csv_shape_select",
            )

            if selected_shape and st.button(
                "Export CSV", key="gen_csv"
            ):
                df = store_data[selected_shape]
                csv = df.to_csv(index=False)
                st.download_button(
                    label=f"Download {selected_shape}.csv",
                    data=csv,
                    file_name=f"{selected_shape}.csv",
                    mime="text/csv",
                )
        else:
            st.caption("No data shapes available.")
    else:
        st.caption("No data in current session.")


render()
