"""AI pre-processing pipeline.

Runs branded detection, intent classification, and topic clustering
on all queries before metric computation. Results are cached in
session state and can be persisted to Supabase.
"""

import logging
from typing import Optional

import pandas as pd

from ai.openrouter_client import OpenRouterClient
from ai.branded_detector import BrandedDetector
from ai.intent_classifier import IntentClassifier
from ai.topic_clusterer import TopicClusterer
from core.data_store import DataStore

logger = logging.getLogger(__name__)


class AIPreprocessor:
    """Orchestrates AI classification of queries."""

    def __init__(
        self,
        client: OpenRouterClient,
        brand_name: str = "",
        cache: Optional[dict] = None,
    ):
        self.client = client
        self.brand_name = brand_name
        self.cache = cache or {}

    def process(
        self,
        store: DataStore,
        progress_callback=None,
    ) -> dict[str, dict]:
        """Run all AI classifications on queries.

        Extracts unique queries from the data store, runs
        branded detection, intent classification, and topic
        clustering. Returns a dict mapping each query to its
        classification results.

        Args:
            store: DataStore with fetched GSC data.
            progress_callback: callable(step, total, message).

        Returns:
            Dict mapping query -> {
                "is_branded": bool,
                "intent": str,
                "topic_cluster": str,
            }
        """
        # Extract all unique queries from available shapes
        queries = self._extract_queries(store)
        if not queries:
            logger.warning("No queries found for AI processing")
            return {}

        total_steps = 3
        step = 0

        def _progress(msg):
            nonlocal step
            step += 1
            if progress_callback:
                progress_callback(step, total_steps, msg)

        # Build per-type caches from existing classifications
        branded_cache = {}
        intent_cache = {}
        topic_cache = {}
        for q, c in self.cache.items():
            if isinstance(c, dict):
                if "is_branded" in c:
                    branded_cache[q] = c["is_branded"]
                if "intent" in c:
                    intent_cache[q] = c["intent"]
                if "topic_cluster" in c:
                    topic_cache[q] = c["topic_cluster"]

        # 1. Branded detection
        _progress("Classifying branded queries...")
        branded_results = {}
        if self.brand_name:
            detector = BrandedDetector(
                client=self.client,
                brand_name=self.brand_name,
                cache=branded_cache,
            )
            branded_results = detector.classify_queries(queries)
        else:
            branded_results = {q: False for q in queries}

        # 2. Intent classification
        _progress("Classifying query intent...")
        classifier = IntentClassifier(
            client=self.client,
            cache=intent_cache,
        )
        intent_results = classifier.classify_queries(queries)

        # 3. Topic clustering
        _progress("Clustering queries by topic...")
        clusterer = TopicClusterer(
            client=self.client,
            cache=topic_cache,
        )
        topic_results = clusterer.cluster_queries(queries)

        # Merge results
        classifications = {}
        for q in queries:
            classifications[q] = {
                "is_branded": branded_results.get(q, False),
                "intent": intent_results.get(
                    q, "informational"
                ),
                "topic_cluster": topic_results.get(
                    q, "uncategorized"
                ),
            }

        logger.info(
            f"AI processing complete: {len(classifications)} "
            f"queries classified"
        )
        return classifications

    @staticmethod
    def _extract_queries(store: DataStore) -> list[str]:
        """Extract unique queries from all query-level shapes."""
        all_queries = set()

        # Check all shapes that have a 'query' column
        query_shapes = [
            "query_90d",
            "query_page_90d",
            "query_date_90d",
            "query_date_30d",
            "query_device_90d",
            "query_country_90d",
        ]

        for shape_name in query_shapes:
            df = store.get_df(shape_name)
            if not df.empty and "query" in df.columns:
                all_queries.update(
                    df["query"].unique().tolist()
                )

        return sorted(all_queries)
