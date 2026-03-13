"""OpenRouter API client for multi-model AI access.

Supports Gemini Flash Lite for classification and Claude Sonnet
for insight generation via the OpenRouter unified API.
"""

import json
import logging
import time
from typing import Optional

import requests
import streamlit as st

logger = logging.getLogger(__name__)

# Model identifiers on OpenRouter
MODELS = {
    "flash_lite": "google/gemini-3.1-flash-lite-preview",
    "sonnet": "anthropic/claude-sonnet-4-5",
}

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterClient:
    """Client for OpenRouter API with retry and batching."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or st.secrets.get(
            "OPENROUTER_API_KEY", ""
        )
        if not self.api_key:
            logger.warning("No OpenRouter API key configured")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def chat(
        self,
        messages: list[dict],
        model: str = "flash_lite",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: Optional[dict] = None,
    ) -> str:
        """Send a chat completion request.

        Args:
            messages: List of message dicts with role/content.
            model: Model key from MODELS dict.
            temperature: Sampling temperature.
            max_tokens: Max response tokens.
            response_format: Optional JSON schema format.

        Returns:
            Response content string.
        """
        model_id = MODELS.get(model, model)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ultimate-gsc-auditor.streamlit.app",
            "X-Title": "Ultimate GSC Auditor",
        }

        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            payload["response_format"] = response_format

        return self._request_with_retry(headers, payload)

    def chat_json(
        self,
        messages: list[dict],
        model: str = "flash_lite",
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> dict:
        """Send a chat request expecting JSON response.

        Returns:
            Parsed JSON dict.
        """
        response_text = self.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

        # Try to parse JSON from response
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            if "```json" in response_text:
                start = response_text.index("```json") + 7
                end = response_text.index("```", start)
                return json.loads(response_text[start:end].strip())
            if "```" in response_text:
                start = response_text.index("```") + 3
                end = response_text.index("```", start)
                return json.loads(response_text[start:end].strip())
            logger.error(
                f"Failed to parse JSON response: "
                f"{response_text[:200]}"
            )
            return {}

    def _request_with_retry(
        self,
        headers: dict,
        payload: dict,
        max_retries: int = 3,
    ) -> str:
        """Make HTTP request with exponential backoff."""
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    OPENROUTER_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=120,
                )

                if response.status_code == 200:
                    data = response.json()
                    return (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )

                if response.status_code == 429:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        f"Rate limited, waiting {wait}s "
                        f"(attempt {attempt + 1})"
                    )
                    time.sleep(wait)
                    continue

                if response.status_code >= 500:
                    wait = 2 ** attempt
                    logger.warning(
                        f"Server error {response.status_code}, "
                        f"retrying in {wait}s"
                    )
                    time.sleep(wait)
                    continue

                logger.error(
                    f"OpenRouter API error {response.status_code}: "
                    f"{response.text[:300]}"
                )
                return ""

            except requests.exceptions.Timeout:
                wait = 2 ** attempt
                logger.warning(
                    f"Request timeout, retrying in {wait}s"
                )
                time.sleep(wait)
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                if attempt == max_retries - 1:
                    return ""
                time.sleep(2 ** attempt)

        return ""
