"""Supabase client for data persistence.

Handles storing and retrieving audit runs, metric results,
raw GSC data, AI classification cache, and URL inspections.
"""

import json
import logging
from datetime import datetime
from typing import Optional

import streamlit as st

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Client for all Supabase read/write operations."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy-initialize Supabase client."""
        if self._client is None:
            try:
                from supabase import create_client

                url = st.secrets.get("SUPABASE_URL", "")
                key = st.secrets.get("SUPABASE_ANON_KEY", "")
                if url and key:
                    self._client = create_client(url, key)
                else:
                    logger.warning(
                        "Supabase not configured "
                        "(missing URL or key)"
                    )
            except Exception as e:
                logger.error(f"Supabase init failed: {e}")
        return self._client

    @property
    def is_configured(self) -> bool:
        return self.client is not None

    # --- Properties ---

    def upsert_property(
        self, property_url: str, display_name: str = ""
    ) -> Optional[dict]:
        """Register or update a GSC property."""
        if not self.is_configured:
            return None
        try:
            result = (
                self.client.table("properties")
                .upsert(
                    {
                        "property_url": property_url,
                        "display_name": (
                            display_name or property_url
                        ),
                        "updated_at": datetime.utcnow()
                        .isoformat(),
                    },
                    on_conflict="property_url",
                )
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Upsert property failed: {e}")
            return None

    def set_background_monitoring(
        self,
        property_url: str,
        enabled: bool,
        refresh_token: Optional[str] = None,
    ) -> bool:
        """Enable or disable background monitoring for a property."""
        if not self.is_configured:
            return False
        try:
            data = {
                "property_url": property_url,
                "background_collection_enabled": enabled,
                "updated_at": datetime.utcnow().isoformat(),
            }
            if refresh_token is not None:
                data["refresh_token"] = refresh_token
            elif not enabled:
                data["refresh_token"] = None

            (
                self.client.table("properties")
                .upsert(data, on_conflict="property_url")
                .execute()
            )
            return True
        except Exception as e:
            logger.error(
                f"Set background monitoring failed: {e}"
            )
            return False

    def get_property(
        self, property_url: str
    ) -> Optional[dict]:
        """Get a property record."""
        if not self.is_configured:
            return None
        try:
            result = (
                self.client.table("properties")
                .select("*")
                .eq("property_url", property_url)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"Get property failed: {e}")
            return None

    # --- Audit Runs ---

    def save_audit_run(self, audit) -> Optional[str]:
        """Save an audit run and return its ID.

        Args:
            audit: AuditResult instance.

        Returns:
            Audit run ID string or None.
        """
        if not self.is_configured:
            return None
        try:
            data = {
                "property_url": audit.property_url,
                "start_date": audit.start_date,
                "end_date": audit.end_date,
                "health_score": audit.health_score,
                "health_grade": audit.health_grade,
                "total_findings": audit.total_findings,
                "severity_counts": audit.severity_counts,
                "metrics_executed": audit.metrics_executed,
                "ai_executive_summary": (
                    audit.ai_executive_summary
                ),
            }

            result = (
                self.client.table("audit_runs")
                .insert(data)
                .execute()
            )

            if result.data:
                run_id = result.data[0].get("id")
                # Save individual metric results
                self._save_metric_results(
                    run_id, audit.results
                )
                # Save AI group analyses
                if audit.ai_group_analyses:
                    self._save_group_analyses(
                        run_id, audit.ai_group_analyses
                    )
                return run_id

        except Exception as e:
            logger.error(f"Save audit run failed: {e}")
        return None

    def _save_metric_results(
        self, run_id: str, results: list
    ) -> None:
        """Save individual metric results for an audit run."""
        rows = []
        for r in results:
            rows.append({
                "audit_run_id": run_id,
                "metric_id": r.metric_id,
                "metric_name": r.metric_name,
                "category": r.category,
                "severity": r.severity.value,
                "summary": r.summary,
                "computed_value": r.computed_value,
                "affected_count": r.affected_count,
                "recommendations": r.recommendations,
                "trend_direction": (
                    r.trend_direction.value
                    if r.trend_direction
                    else None
                ),
            })

        # Insert in batches of 50
        for i in range(0, len(rows), 50):
            batch = rows[i:i + 50]
            try:
                (
                    self.client.table("metric_results")
                    .insert(batch)
                    .execute()
                )
            except Exception as e:
                logger.error(
                    f"Save metric results batch failed: {e}"
                )

    def _save_group_analyses(
        self, run_id: str, analyses: dict[str, str]
    ) -> None:
        """Save AI group narratives for an audit run."""
        rows = [
            {
                "audit_run_id": run_id,
                "category": cat,
                "narrative": text,
            }
            for cat, text in analyses.items()
        ]
        try:
            (
                self.client.table("ai_group_analyses")
                .insert(rows)
                .execute()
            )
        except Exception as e:
            logger.error(f"Save group analyses failed: {e}")

    def get_audit_history(
        self, property_url: str, limit: int = 20
    ) -> list[dict]:
        """Get audit run history for a property."""
        if not self.is_configured:
            return []
        try:
            result = (
                self.client.table("audit_runs")
                .select("*")
                .eq("property_url", property_url)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Get audit history failed: {e}")
            return []

    def get_audit_run_results(
        self, run_id: str
    ) -> list[dict]:
        """Get metric results for a specific audit run."""
        if not self.is_configured:
            return []
        try:
            result = (
                self.client.table("metric_results")
                .select("*")
                .eq("audit_run_id", run_id)
                .order("metric_id")
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Get audit results failed: {e}")
            return []

    # --- AI Classification Cache ---

    def get_cached_classifications(
        self, property_url: str
    ) -> dict[str, dict]:
        """Load cached AI classifications for a property."""
        if not self.is_configured:
            return {}
        try:
            result = (
                self.client.table("ai_classifications")
                .select("query,is_branded,intent,topic_cluster")
                .eq("property_url", property_url)
                .execute()
            )
            cache = {}
            for row in (result.data or []):
                cache[row["query"]] = {
                    "is_branded": row.get("is_branded", False),
                    "intent": row.get(
                        "intent", "informational"
                    ),
                    "topic_cluster": row.get(
                        "topic_cluster", "uncategorized"
                    ),
                }
            return cache
        except Exception as e:
            logger.error(
                f"Get cached classifications failed: {e}"
            )
            return {}

    def save_classifications(
        self,
        property_url: str,
        classifications: dict[str, dict],
    ) -> None:
        """Save AI classifications to cache."""
        if not self.is_configured:
            return
        rows = []
        for query, data in classifications.items():
            rows.append({
                "property_url": property_url,
                "query": query,
                "is_branded": data.get("is_branded", False),
                "intent": data.get(
                    "intent", "informational"
                ),
                "topic_cluster": data.get(
                    "topic_cluster", "uncategorized"
                ),
            })

        # Upsert in batches
        for i in range(0, len(rows), 100):
            batch = rows[i:i + 100]
            try:
                (
                    self.client.table("ai_classifications")
                    .upsert(
                        batch,
                        on_conflict="property_url,query",
                    )
                    .execute()
                )
            except Exception as e:
                logger.error(
                    f"Save classifications batch failed: {e}"
                )

    # --- Raw GSC Data Archive ---

    def archive_raw_data(
        self,
        property_url: str,
        shape_name: str,
        df,
    ) -> None:
        """Archive raw GSC data for historical tracking."""
        if not self.is_configured or df.empty:
            return
        try:
            records = df.to_dict(orient="records")
            rows = []
            for record in records:
                # Convert any non-serializable types
                clean = {}
                for k, v in record.items():
                    if hasattr(v, "isoformat"):
                        clean[k] = v.isoformat()
                    else:
                        clean[k] = v

                rows.append({
                    "property_url": property_url,
                    "shape_name": shape_name,
                    "data": clean,
                })

            # Insert in batches
            for i in range(0, len(rows), 500):
                batch = rows[i:i + 500]
                (
                    self.client.table("gsc_raw_data")
                    .insert(batch)
                    .execute()
                )

        except Exception as e:
            logger.error(
                f"Archive raw data failed for "
                f"{shape_name}: {e}"
            )

    # --- URL Inspection Cache ---

    def save_url_inspections(
        self,
        property_url: str,
        inspections: dict[str, dict],
    ) -> None:
        """Cache URL inspection results."""
        if not self.is_configured:
            return
        rows = []
        for url, result in inspections.items():
            rows.append({
                "property_url": property_url,
                "url": url,
                "inspection_result": result,
            })

        for i in range(0, len(rows), 100):
            batch = rows[i:i + 100]
            try:
                (
                    self.client.table(
                        "url_inspection_results"
                    )
                    .upsert(
                        batch,
                        on_conflict="property_url,url",
                    )
                    .execute()
                )
            except Exception as e:
                logger.error(
                    f"Save URL inspections failed: {e}"
                )

    def get_cached_inspections(
        self, property_url: str
    ) -> dict[str, dict]:
        """Load cached URL inspection results."""
        if not self.is_configured:
            return {}
        try:
            result = (
                self.client.table(
                    "url_inspection_results"
                )
                .select("url,inspection_result")
                .eq("property_url", property_url)
                .execute()
            )
            return {
                row["url"]: row["inspection_result"]
                for row in (result.data or [])
            }
        except Exception as e:
            logger.error(
                f"Get cached inspections failed: {e}"
            )
            return {}
