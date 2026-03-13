"""AI-powered search intent classification.

Uses Gemini Flash Lite to classify queries into four intent types:
informational, transactional, navigational, commercial.
"""

import logging
from typing import Optional

from ai.openrouter_client import OpenRouterClient
from ai.prompt_templates import (
    INTENT_CLASSIFICATION_SYSTEM,
    INTENT_CLASSIFICATION_USER,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
VALID_INTENTS = {
    "informational", "transactional",
    "navigational", "commercial",
}


class IntentClassifier:
    """Classifies search query intent using AI."""

    def __init__(
        self,
        client: OpenRouterClient,
        cache: Optional[dict] = None,
    ):
        self.client = client
        self.cache = cache or {}

    def classify_queries(
        self,
        queries: list[str],
        progress_callback=None,
    ) -> dict[str, str]:
        """Classify all queries by search intent.

        Args:
            queries: List of search queries.
            progress_callback: Optional callable(current, total).

        Returns:
            Dict mapping query -> intent string.
        """
        results = dict(self.cache)
        uncached = [q for q in queries if q not in results]

        if not uncached:
            logger.info("All queries already classified (cached)")
            return results

        logger.info(
            f"Classifying intent for {len(uncached)} queries "
            f"({len(results)} cached)"
        )

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
    ) -> dict[str, str]:
        """Classify a single batch of queries."""
        query_list = "\n".join(f"- {q}" for q in queries)

        messages = [
            {
                "role": "system",
                "content": INTENT_CLASSIFICATION_SYSTEM,
            },
            {
                "role": "user",
                "content": INTENT_CLASSIFICATION_USER.format(
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

            result = {}
            response_lower = {
                k.lower().strip(): v
                for k, v in response.items()
            }

            for q in queries:
                q_lower = q.lower().strip()
                intent = response_lower.get(q_lower, "")
                if isinstance(intent, str):
                    intent = intent.lower().strip()
                if intent in VALID_INTENTS:
                    result[q] = intent
                else:
                    result[q] = self._heuristic_intent(q)

            return result

        except Exception as e:
            logger.error(f"Intent classification failed: {e}")
            return {
                q: self._heuristic_intent(q)
                for q in queries
            }

    @staticmethod
    def _heuristic_intent(query: str) -> str:
        """Fallback heuristic intent classification."""
        q = query.lower()

        transactional_signals = [
            "buy", "price", "cost", "order", "purchase",
            "deal", "discount", "coupon", "cheap", "affordable",
            "hire", "book", "subscribe",
        ]
        commercial_signals = [
            "best", "top", "review", "compare", "vs",
            "alternative", "recommended",
        ]
        informational_signals = [
            "how", "what", "why", "when", "where", "who",
            "guide", "tutorial", "tips", "learn", "example",
        ]

        for signal in transactional_signals:
            if signal in q:
                return "transactional"
        for signal in commercial_signals:
            if signal in q:
                return "commercial"
        for signal in informational_signals:
            if signal in q:
                return "informational"

        return "informational"
