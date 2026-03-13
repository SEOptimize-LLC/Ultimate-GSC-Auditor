"""Excel export for GSC audit results.

Creates a multi-sheet workbook with summary, findings by category,
and data tables.
"""

import io
from typing import Optional

import pandas as pd

from models.audit_result import AuditResult
from models.data_shapes import METRIC_CATEGORIES


def generate_excel_report(audit: AuditResult) -> bytes:
    """Generate a multi-sheet Excel workbook.

    Sheets:
    - Summary: Health score, severity counts, metadata
    - All Findings: Every metric result in one table
    - Per-category sheets: Detailed findings per category
    - Top Findings: Top 20 most severe findings

    Args:
        audit: Completed AuditResult.

    Returns:
        Excel file as bytes.
    """
    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer, engine="openpyxl"
    ) as writer:
        # Sheet 1: Summary
        summary_data = {
            "Property": [audit.property_url],
            "Start Date": [audit.start_date],
            "End Date": [audit.end_date],
            "Health Score": [audit.health_score],
            "Health Grade": [audit.health_grade],
            "Total Findings": [audit.total_findings],
            "Metrics Executed": [
                len(audit.metrics_executed)
            ],
        }
        # Add severity counts
        for sev, count in audit.severity_counts.items():
            summary_data[f"{sev.title()} Count"] = [count]

        pd.DataFrame(summary_data).to_excel(
            writer, sheet_name="Summary", index=False
        )

        # Sheet 2: All Findings
        all_rows = _results_to_rows(audit.results)
        if all_rows:
            pd.DataFrame(all_rows).to_excel(
                writer, sheet_name="All Findings", index=False
            )

        # Sheet 3: Top Findings
        top = audit.get_top_findings(20)
        top_rows = _results_to_rows(top)
        if top_rows:
            pd.DataFrame(top_rows).to_excel(
                writer, sheet_name="Top Findings", index=False
            )

        # Per-category sheets
        for cat_name in METRIC_CATEGORIES:
            cat_results = audit.results_by_category.get(
                cat_name, []
            )
            if not cat_results:
                continue

            # Excel sheet names limited to 31 chars
            sheet_name = cat_name[:31]
            cat_rows = _results_to_rows(cat_results)
            if cat_rows:
                pd.DataFrame(cat_rows).to_excel(
                    writer,
                    sheet_name=sheet_name,
                    index=False,
                )

            # Add data tables for this category
            for r in cat_results:
                if (
                    r.data_table is not None
                    and not r.data_table.empty
                ):
                    dt_name = (
                        f"Data_{r.metric_id}"
                    )[:31]
                    r.data_table.head(50).to_excel(
                        writer,
                        sheet_name=dt_name,
                        index=False,
                    )

    return buffer.getvalue()


def _results_to_rows(results) -> list[dict]:
    """Convert MetricResult list to flat dict rows."""
    rows = []
    for r in results:
        row = {
            "Metric ID": r.metric_id,
            "Metric Name": r.metric_name,
            "Category": r.category,
            "Severity": r.severity.value.title(),
            "Summary": r.summary,
            "Computed Value": r.computed_value,
            "Affected Count": r.affected_count,
        }

        if r.opportunity_value:
            row["Opportunity"] = r.opportunity_value
        if r.trend_direction:
            row["Trend"] = r.trend_direction.value.title()
        if r.benchmark_comparison:
            row["Benchmark"] = r.benchmark_comparison
        if r.recommendations:
            row["Recommendations"] = " | ".join(
                r.recommendations
            )

        rows.append(row)
    return rows
