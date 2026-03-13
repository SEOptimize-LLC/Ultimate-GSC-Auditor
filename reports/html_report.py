"""HTML report generator for GSC audit results."""

from models.audit_result import AuditResult
from models.data_shapes import METRIC_CATEGORIES
from reports.markdown_report import generate_markdown_report


def _severity_badge(severity_value: str) -> str:
    """Create an HTML badge for severity."""
    colors = {
        "critical": "#DC3545",
        "high": "#FD7E14",
        "medium": "#FFC107",
        "low": "#0D6EFD",
        "insight": "#6C757D",
    }
    color = colors.get(severity_value, "#6C757D")
    text_color = "#fff" if severity_value != "medium" else "#000"
    return (
        f'<span style="background:{color};color:{text_color};'
        f'padding:2px 8px;border-radius:4px;font-size:0.85em;">'
        f'{severity_value.title()}</span>'
    )


def _grade_color(grade: str) -> str:
    """Get color for health grade."""
    return {
        "A": "#28A745", "B": "#5CB85C",
        "C": "#FFC107", "D": "#FD7E14", "F": "#DC3545",
    }.get(grade, "#6C757D")


def generate_html_report(audit: AuditResult) -> str:
    """Generate a styled HTML report.

    Args:
        audit: Completed AuditResult.

    Returns:
        Full HTML document string.
    """
    grade_color = _grade_color(audit.health_grade)

    # Build severity distribution
    sev_rows = ""
    for sev, count in audit.severity_counts.items():
        if count > 0:
            sev_rows += (
                f"<tr><td>{_severity_badge(sev)}</td>"
                f"<td>{count}</td></tr>\n"
            )

    # Build top findings
    findings_html = ""
    for i, r in enumerate(audit.get_top_findings(10), 1):
        recs_html = ""
        if r.recommendations:
            recs_html = "<ul>" + "".join(
                f"<li>{rec}</li>" for rec in r.recommendations
            ) + "</ul>"

        val_html = ""
        if r.computed_value is not None:
            val_html = (
                f"<p><strong>Value:</strong> "
                f"{r.computed_value:.2f}</p>"
            )

        findings_html += f"""
        <div class="finding">
            <h3>{i}. {r.metric_name}
                {_severity_badge(r.severity.value)}</h3>
            <p><strong>Category:</strong> {r.category}</p>
            <p>{r.summary}</p>
            {val_html}
            {recs_html}
        </div>
        """

    # Build category sections
    categories_html = ""
    for category in METRIC_CATEGORIES:
        cat_results = audit.results_by_category.get(
            category, []
        )
        if not cat_results:
            continue

        narrative = audit.ai_group_analyses.get(category, "")
        narrative_html = (
            f"<p>{narrative}</p>" if narrative else ""
        )

        rows = ""
        for r in sorted(
            cat_results, key=lambda x: x.severity.priority
        ):
            val = (
                f"{r.computed_value:.2f}"
                if r.computed_value is not None
                else "&mdash;"
            )
            summary_short = r.summary[:80]
            rows += f"""
            <tr>
                <td>{r.metric_name}</td>
                <td>{_severity_badge(r.severity.value)}</td>
                <td>{val}</td>
                <td>{r.affected_count:,}</td>
                <td>{summary_short}</td>
            </tr>
            """

        categories_html += f"""
        <div class="category">
            <h3>{category}</h3>
            {narrative_html}
            <table>
                <thead>
                    <tr>
                        <th>Metric</th>
                        <th>Severity</th>
                        <th>Value</th>
                        <th>Affected</th>
                        <th>Summary</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
        """

    # Executive summary
    exec_html = ""
    if audit.ai_executive_summary:
        paragraphs = audit.ai_executive_summary.split("\n\n")
        exec_html = "".join(
            f"<p>{p}</p>" for p in paragraphs if p.strip()
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width">
    <title>GSC Audit: {audit.property_url}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont,
                'Segoe UI', Roboto, sans-serif;
            color: #333; max-width: 1000px;
            margin: 0 auto; padding: 24px;
            background: #fafafa;
        }}
        h1 {{ color: #1a1a2e; margin-bottom: 8px; }}
        h2 {{
            color: #1a1a2e; margin: 32px 0 16px;
            border-bottom: 2px solid #eee; padding-bottom: 8px;
        }}
        h3 {{ color: #333; margin: 16px 0 8px; }}
        .header-meta {{
            color: #666; margin-bottom: 24px;
            font-size: 0.95em;
        }}
        .score-card {{
            display: flex; gap: 24px; margin: 24px 0;
            flex-wrap: wrap;
        }}
        .score-item {{
            background: #fff; border-radius: 8px;
            padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.1);
            text-align: center; min-width: 120px;
        }}
        .grade {{
            font-size: 3em; font-weight: bold;
            color: {grade_color};
        }}
        .score-label {{
            font-size: 0.85em; color: #888;
            margin-top: 4px;
        }}
        table {{
            width: 100%; border-collapse: collapse;
            margin: 12px 0; font-size: 0.9em;
        }}
        th, td {{
            padding: 8px 12px; text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{ background: #f5f5f5; font-weight: 600; }}
        .finding {{
            background: #fff; border-radius: 6px;
            padding: 16px; margin: 12px 0;
            box-shadow: 0 1px 3px rgba(0,0,0,.08);
        }}
        .finding h3 {{ margin-top: 0; }}
        .category {{
            background: #fff; border-radius: 6px;
            padding: 16px; margin: 16px 0;
            box-shadow: 0 1px 3px rgba(0,0,0,.08);
        }}
        ul {{ margin: 8px 0; padding-left: 24px; }}
        li {{ margin: 4px 0; }}
        .footer {{
            margin-top: 48px; padding-top: 16px;
            border-top: 1px solid #ddd; color: #999;
            font-size: 0.85em; text-align: center;
        }}
    </style>
</head>
<body>
    <h1>GSC Audit Report</h1>
    <div class="header-meta">
        <p><strong>{audit.property_url}</strong></p>
        <p>{audit.start_date} to {audit.end_date}</p>
    </div>

    <div class="score-card">
        <div class="score-item">
            <div class="grade">{audit.health_grade}</div>
            <div class="score-label">Health Grade</div>
        </div>
        <div class="score-item">
            <div style="font-size:2em;font-weight:bold;">
                {audit.health_score}
            </div>
            <div class="score-label">Health Score</div>
        </div>
        <div class="score-item">
            <div style="font-size:2em;font-weight:bold;">
                {audit.total_findings}
            </div>
            <div class="score-label">Findings</div>
        </div>
        <div class="score-item">
            <div style="font-size:2em;font-weight:bold;">
                {len(audit.metrics_executed)}
            </div>
            <div class="score-label">Metrics</div>
        </div>
    </div>

    <h2>Severity Distribution</h2>
    <table>
        <thead>
            <tr><th>Severity</th><th>Count</th></tr>
        </thead>
        <tbody>{sev_rows}</tbody>
    </table>

    {"<h2>Executive Summary</h2>" + exec_html
     if exec_html else ""}

    <h2>Top Findings</h2>
    {findings_html}

    <h2>Category Analysis</h2>
    {categories_html}

    <div class="footer">
        Generated by Ultimate GSC Auditor
    </div>
</body>
</html>"""

    return html
