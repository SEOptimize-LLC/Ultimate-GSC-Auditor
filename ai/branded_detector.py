"""AI-powered branded query detection.

Uses Gemini Flash Lite to classify queries as branded/non-branded,
catching misspellings and abbreviations that simple string matching
would miss.
"""

import logging
from typing import Optional

from ai.openrouter_client import OpenRouterClient
from ai.prompt_templates import (
    BRANDED_DETECTION_SYSTEM,
    BRANDED_DETECTION_USER,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


class BrandedDetector:
    """Classifies queries as branded or non-branded using AI."""

    def __init__(
        self,
        client: OpenRouterClient,
        brand_name: str,
        cache: Optional[dict] = None,
    ):
        self.client = client
        self.brand_name = brand_name
        self.cache = cache or {}

    def classify_queries(
        self,
        queries: list[str],
        progress_callback=None,
    ) -> dict[str, bool]:
        """Classify all queries as branded or non-branded.

        Args:
            queries: List of search queries to classify.
            progress_callback: Optional callable(current, total).

        Returns:
            Dict mapping query -> is_branded (bool).
        """
        results = dict(self.cache)

        # Filter out already-classified queries
        uncached = [q for q in queries if q not in results]

        if not uncached:
            logger.info("All queries already classified (cached)")
            return results

        logger.info(
            f"Classifying {len(uncached)} queries "
            f"({len(results)} cached)"
        )

        # Process in batches
        total_batches = (
            (len(uncached) + BATCH_SIZE - 1) // BATCH_SIZE
        )

        for i in range(0, len(uncached), BATCH_SIZE):
            batch = uncached[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1

            if progress_callback:
                progress_callback(batch_num, total_batches)

            batch_results = self._classify_batch(batch)
            results.update(batch_results)

        return results

    def _classify_batch(
        self, queries: list[str]
    ) -> dict[str, bool]:
        """Classify a single batch of queries."""
        query_list = "\n".join(
            f"- {q}" for q in queries
        )

        messages = [
            {"role": "system", "content": BRANDED_DETECTION_SYSTEM},
            {
                "role": "user",
                "content": BRANDED_DETECTION_USER.format(
                    brand_name=self.brand_name,
                    queries=query_list,
                ),
            },
        ]

        try:
            response = self.client.chat_json(
                messages=messages,
                model="flash_lite",
                temperature=0.0,
            )

            # Normalize response keys to match input queries
            result = {}
            response_lower = {
                k.lower().strip(): v
                for k, v in response.items()
            }

            for q in queries:
                q_lower = q.lower().strip()
                if q_lower in response_lower:
                    result[q] = bool(response_lower[q_lower])
                else:
                    # Fallback: simple string matching
                    result[q] = (
                        self.brand_name.lower() in q.lower()
                    )

            return result

        except Exception as e:
            logger.error(f"Branded detection batch failed: {e}")
            # Fallback for entire batch
            return {
                q: self.brand_name.lower() in q.lower()
                for q in queries
            }
