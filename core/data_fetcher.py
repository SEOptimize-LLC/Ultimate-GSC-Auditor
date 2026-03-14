"""Smart data fetching orchestrator.

Determines which GSC API calls are needed based on selected metrics,
fetches each unique data shape once, and stores results in DataStore.
"""

import logging
import time
from typing import Optional

import pandas as pd
import streamlit as st

from core.data_store import DataStore
from core.gsc_client import GSCClient
from models.data_shapes import (
    SHAPES,
    METRICS_NEEDING_SITEMAPS,
    METRICS_NEEDING_URL_INSPECTION,
    get_required_shapes,
    needs_url_inspection,
    needs_sitemaps,
)
from utils.date_utils import get_date_range

logger = logging.getLogger(__name__)


class DataFetcher:
    """Orchestrates all GSC data fetching based on selected metrics."""

    def __init__(
        self,
        client: GSCClient,
        store: DataStore,
        site_url: str,
    ):
        self.client = client
        self.store = store
        self.site_url = site_url

    def fetch_for_metrics(
        self,
        metric_ids: list[int],
        progress_callback=None,
        url_filter=None,
        skip_url_inspection: bool = False,
    ) -> None:
        """Fetch all data shapes required by the given metric IDs.

        Args:
            metric_ids: List of metric IDs (1-100) to fetch data for.
            progress_callback: Optional callable(current, total, message).
            url_filter: Optional URLFilterConfig to filter page-level data.
            skip_url_inspection: If True, skip URL inspection (run separately).
        """
        required = get_required_shapes(metric_ids)
        shapes_to_fetch = [
            s for s in required
            if s in SHAPES and not self.store.has(SHAPES[s].name)
        ]

        needs_inspection = (
            not skip_url_inspection
            and needs_url_inspection(metric_ids)
            and not self.store.has("url_inspection")
        )
        needs_sitemap = (
            needs_sitemaps(metric_ids)
            and not self.store.has("sitemaps")
        )

        total_steps = (
            len(shapes_to_fetch)
            + int(needs_inspection)
            + int(needs_sitemap)
        )
        current_step = 0

        def _progress(msg: str):
            nonlocal current_step
            current_step += 1
            if progress_callback:
                progress_callback(current_step, total_steps, msg)

        # Fetch search analytics shapes
        for shape_key in shapes_to_fetch:
            shape = SHAPES[shape_key]
            start_date, end_date = get_date_range(shape.days)
            logger.info(f"Fetching shape {shape_key}: {shape.description}")

            try:
                if shape.search_type != "web":
                    df = self.client.query_search_analytics_by_type(
                        site_url=self.site_url,
                        start_date=start_date,
                        end_date=end_date,
                        dimensions=list(shape.dimensions),
                        search_type=shape.search_type,
                    )
                else:
                    df = self.client.query_search_analytics_all(
                        site_url=self.site_url,
                        start_date=start_date,
                        end_date=end_date,
                        dimensions=list(shape.dimensions),
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to fetch shape {shape_key} "
                    f"({shape.description}): {e}"
                )
                df = pd.DataFrame(
                    columns=list(shape.dimensions)
                    + ["clicks", "impressions", "ctr", "position"]
                )

            # Apply URL filtering to page-dimension shapes
            if url_filter and "page" in shape.dimensions and not df.empty:
                df = self._apply_url_filter(df, url_filter)

            self.store.set(shape.name, df)
            _progress(f"Fetched {shape.description} ({len(df):,} rows)")

        # Fetch sitemaps
        if needs_sitemap:
            self._fetch_sitemaps()
            _progress("Fetched sitemap data")

        # Fetch URL inspections
        if needs_inspection:
            self.fetch_url_inspections(
                url_filter=url_filter,
                progress_callback=progress_callback,
            )
            _progress("Fetched URL inspection data")

    def _apply_url_filter(
        self, df: pd.DataFrame, url_filter
    ) -> pd.DataFrame:
        """Apply URL filter to a DataFrame containing a 'page' column."""
        if df.empty or "page" not in df.columns:
            return df

        mask = df["page"].apply(url_filter.should_include)
        filtered = df[mask].reset_index(drop=True)
        excluded_count = len(df) - len(filtered)
        if excluded_count > 0:
            logger.info(
                f"URL filter excluded {excluded_count} rows "
                f"({len(filtered)} remaining)"
            )
        return filtered

    def _fetch_sitemaps(self) -> None:
        """Fetch sitemap data from GSC."""
        try:
            sitemaps = self.client.list_sitemaps(self.site_url)
            self.store.set("sitemaps", sitemaps)
        except Exception as e:
            logger.error(f"Failed to fetch sitemaps: {e}")
            self.store.set("sitemaps", [])

    def fetch_url_inspections(
        self, url_filter=None, progress_callback=None
    ) -> None:
        """Fetch URL inspection data for SEO-relevant URLs.

        Uses the URL filter to focus on pages that matter:
        homepage, service/product pages, and blog posts.
        Limited by the 2,000/day per property API quota.
        """
        page_df = self.store.get_df("page_90d")
        if page_df.empty:
            self.store.set("url_inspection", {})
            return

        # Get all unique URLs from page data
        all_urls = page_df["page"].unique().tolist()

        # Apply URL filter if provided
        if url_filter:
            included, _ = url_filter.filter_urls(all_urls)
            urls_to_inspect = included
        else:
            urls_to_inspect = all_urls

        # Cap at 2,000 (daily API limit per property).
        # Prioritize by impressions.
        if len(urls_to_inspect) > 2000:
            url_impressions = (
                page_df[page_df["page"].isin(urls_to_inspect)]
                .groupby("page")["impressions"]
                .sum()
                .sort_values(ascending=False)
            )
            urls_to_inspect = (
                url_impressions.head(2000).index.tolist()
            )

        logger.info(
            f"Inspecting {len(urls_to_inspect)} URLs "
            f"(filtered from {len(all_urls)} total)"
        )

        results = self.client.inspect_urls_batch(
            site_url=self.site_url,
            urls=urls_to_inspect,
            progress_callback=progress_callback,
        )
        self.store.set("url_inspection", results)

    @property
    def fetch_summary(self) -> dict:
        """Get a summary of what has been fetched."""
        return {
            "shapes_fetched": self.store.fetched_shapes,
            "memory_usage_mb": round(self.store.memory_usage_mb, 2),
        }
