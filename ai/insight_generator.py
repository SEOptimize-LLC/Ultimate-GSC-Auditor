"""AI insight generation — group narratives and executive summary.

Uses Claude Sonnet for high-quality analysis and synthesis.
"""

import json
import logging
from typing import Optional

from ai.openrouter_client import OpenRouterClient
from ai.prompt_templates import (
    GROUP_NARRATIVE_SYSTEM,
    GROUP_NARRATIVE_USER,
    EXECUTIVE_SUMMARY_SYSTEM,
    EXECUTIVE_SUMMARY_USER,
    CONTENT_PLAN_SYSTEM,
    CONTENT_PLAN_USER,
)
from models.audit_result import AuditResult

logger = logging.getLogger(__name__)


class InsightGenerator:
    """Generates AI-powered narratives and executive summaries."""

    def __init__(self, client: OpenRouterClient):
        self.client = client

    def generate_group_narratives(
        self,
        audit: AuditResult,
        progress_callback=None,
    ) -> dict[str, str]:
        """Generate a narrative for each metric category.

        Args:
            audit: Completed audit result.
            progress_callback: Optional callable(current, total).

        Returns:
            Dict mapping category name -> narrative text.
        """
        categories = audit.results_by_category
        narratives = {}
        total = len(categories)

        for i, (category, results) in enumerate(
            categories.items()
        ):
            if progress_callback:
                progress_callback(i + 1, total)

            # Format metric results for the prompt
            results_text = self._format_results(results)

            messages = [
                {
                    "role": "system",
                    "content": GROUP_NARRATIVE_SYSTEM,
                },
                {
                    "role": "user",
                    "content": GROUP_NARRATIVE_USER.format(
                        category=category,
                        property_url=audit.property_url,
                        start_date=audit.start_date,
                        end_date=audit.end_date,
                        metric_results=results_text,
                    ),
                },
            ]

            narrative = self.client.chat(
                messages=messages,
                model="sonnet",
                temperature=0.3,
                max_tokens=2048,
            )

            if narrative:
                narratives[category] = narrative
            else:
                narratives[category] = (
                    f"Analysis for {category} could not be "
                    f"generated. {len(results)} metrics were "
                    f"computed in this category."
                )

        return narratives

    def generate_executive_summary(
        self,
        audit: AuditResult,
        category_narratives: dict[str, str],
    ) -> str:
        """Generate an executive summary from all narratives.

        Args:
            audit: Completed audit result.
            category_narratives: Narratives from each category.

        Returns:
            Executive summary text.
        """
        sev_text = "\n".join(
            f"- {sev.title()}: {count}"
            for sev, count in audit.severity_counts.items()
            if count > 0
        )

        narratives_text = "\n\n".join(
            f"### {cat}\n{text}"
            for cat, text in category_narratives.items()
        )

        messages = [
            {
                "role": "system",
                "content": EXECUTIVE_SUMMARY_SYSTEM,
            },
            {
                "role": "user",
                "content": EXECUTIVE_SUMMARY_USER.format(
                    property_url=audit.property_url,
                    health_score=audit.health_score,
                    health_grade=audit.health_grade,
                    start_date=audit.start_date,
                    end_date=audit.end_date,
                    severity_counts=sev_text,
                    category_narratives=narratives_text,
                ),
            },
        ]

        summary = self.client.chat(
            messages=messages,
            model="sonnet",
            temperature=0.3,
            max_tokens=4096,
        )

        return summary or (
            "Executive summary could not be generated."
        )

    def generate_content_plan(
        self,
        audit: AuditResult,
    ) -> Optional[dict]:
        """Generate a prioritized content plan.

        Returns:
            Dict with this_week, this_month, this_quarter keys,
            or None if generation fails.
        """
        top_findings = audit.get_top_findings(15)
        findings_text = "\n".join(
            f"- [{r.severity.value.upper()}] {r.metric_name}: "
            f"{r.summary}"
            for r in top_findings
        )

        # Extract query/content summaries
        query_results = audit.results_by_category.get(
            "Query Performance", []
        )
        query_text = "\n".join(
            f"- {r.metric_name}: {r.summary}"
            for r in query_results[:5]
        )

        content_results = (
            audit.results_by_category.get(
                "Content Health & Decay", []
            )
            + audit.results_by_category.get(
                "Content Portfolio & Library Health", []
            )
        )
        content_text = "\n".join(
            f"- {r.metric_name}: {r.summary}"
            for r in content_results[:5]
        )

        messages = [
            {"role": "system", "content": CONTENT_PLAN_SYSTEM},
            {
                "role": "user",
                "content": CONTENT_PLAN_USER.format(
                    property_url=audit.property_url,
                    health_score=audit.health_score,
                    top_findings=findings_text,
                    query_summary=query_text or "N/A",
                    content_summary=content_text or "N/A",
                ),
            },
        ]

        result = self.client.chat_json(
            messages=messages,
            model="sonnet",
            temperature=0.3,
            max_tokens=4096,
        )

        if result and any(
            k in result
            for k in ("this_week", "this_month", "this_quarter")
        ):
            return result

        return None

    @staticmethod
    def _format_results(results) -> str:
        """Format metric results for prompt consumption."""
        parts = []
        for r in results:
            part = (
                f"**{r.metric_name}** "
                f"(ID: {r.metric_id}, "
                f"Severity: {r.severity.value})\n"
                f"Summary: {r.summary}"
            )
            if r.computed_value is not None:
                part += f"\nValue: {r.computed_value:.2f}"
            if r.affected_count > 0:
                part += f"\nAffected: {r.affected_count:,}"
            if r.recommendations:
                recs = "; ".join(r.recommendations[:2])
                part += f"\nRecommendations: {recs}"
            parts.append(part)
        return "\n\n".join(parts)
