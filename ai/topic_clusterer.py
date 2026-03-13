"""AI-powered topic clustering for search queries.

Uses Gemini Flash Lite to group queries into topic clusters.
Two-stage process: batch clustering then label consolidation.
"""

import logging
from typing import Optional

from ai.openrouter_client import OpenRouterClient
from ai.prompt_templates import (
    TOPIC_CLUSTERING_SYSTEM,
    TOPIC_CLUSTERING_USER,
    TOPIC_CONSOLIDATION_SYSTEM,
    TOPIC_CONSOLIDATION_USER,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 200


class TopicClusterer:
    """Groups queries into topic clusters using AI."""

    def __init__(
        self,
        client: OpenRouterClient,
        cache: Optional[dict] = None,
    ):
        self.client = client
        self.cache = cache or {}

    def cluster_queries(
        self,
        queries: list[str],
        progress_callback=None,
    ) -> dict[str, str]:
        """Assign topic clusters to all queries.

        Two-stage process:
        1. Batch clustering: groups of ~200 queries
        2. Label consolidation: merge similar cluster names

        Args:
            queries: List of search queries.
            progress_callback: Optional callable(current, total).

        Returns:
            Dict mapping query -> cluster name.
        """
        results = dict(self.cache)
        uncached = [q for q in queries if q not in results]

        if not uncached:
            logger.info(
                "All queries already clustered (cached)"
            )
            return results

        logger.info(
            f"Clustering {len(uncached)} queries "
            f"({len(results)} cached)"
        )

        # Stage 1: Batch clustering
        total_batches = (
            (len(uncached) + BATCH_SIZE - 1) // BATCH_SIZE
        )
        # +1 for consolidation step
        total_steps = total_batches + 1

        batch_results = {}
        for i in range(0, len(uncached), BATCH_SIZE):
            batch = uncached[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1

            if progress_callback:
                progress_callback(batch_num, total_steps)

            result = self._cluster_batch(batch)
            batch_results.update(result)

        # Stage 2: Consolidate cluster labels
        if progress_callback:
            progress_callback(total_steps, total_steps)

        all_labels = set(batch_results.values())
        if len(all_labels) > 10:
            label_map = self._consolidate_labels(
                list(all_labels)
            )
            for query, label in batch_results.items():
                canonical = label_map.get(label, label)
                batch_results[query] = canonical

        results.update(batch_results)
        return results

    def _cluster_batch(
        self, queries: list[str]
    ) -> dict[str, str]:
        """Cluster a single batch of queries."""
        query_list = "\n".join(f"- {q}" for q in queries)

        messages = [
            {
                "role": "system",
                "content": TOPIC_CLUSTERING_SYSTEM,
            },
            {
                "role": "user",
                "content": TOPIC_CLUSTERING_USER.format(
                    queries=query_list,
                ),
            },
        ]

        try:
            response = self.client.chat_json(
                messages=messages,
                model="flash_lite",
                temperature=0.1,
                max_tokens=8192,
            )

            result = {}
            response_lower = {
                k.lower().strip(): v
                for k, v in response.items()
            }

            for q in queries:
                q_lower = q.lower().strip()
                cluster = response_lower.get(q_lower, "")
                if isinstance(cluster, str) and cluster.strip():
                    result[q] = cluster.strip()
                else:
                    result[q] = "uncategorized"

            return result

        except Exception as e:
            logger.error(f"Topic clustering failed: {e}")
            return {q: "uncategorized" for q in queries}

    def _consolidate_labels(
        self, labels: list[str]
    ) -> dict[str, str]:
        """Merge similar cluster labels into canonical names."""
        label_list = "\n".join(f"- {l}" for l in labels)

        messages = [
            {
                "role": "system",
                "content": TOPIC_CONSOLIDATION_SYSTEM,
            },
            {
                "role": "user",
                "content": TOPIC_CONSOLIDATION_USER.format(
                    cluster_names=label_list,
                ),
            },
        ]

        try:
            response = self.client.chat_json(
                messages=messages,
                model="flash_lite",
                temperature=0.0,
            )

            # Build mapping, keeping original if not in response
            mapping = {}
            for label in labels:
                canonical = response.get(label, label)
                if isinstance(canonical, str) and canonical:
                    mapping[label] = canonical.strip()
                else:
                    mapping[label] = label

            return mapping

        except Exception as e:
            logger.error(f"Label consolidation failed: {e}")
            return {l: l for l in labels}
