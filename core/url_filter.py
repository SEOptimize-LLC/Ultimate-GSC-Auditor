"""URL inclusion/exclusion engine.

Applies URL filtering rules to remove non-SEO pages from analysis.
Runs before any metric computation to ensure only relevant URLs
are included in the audit.
"""

import logging
from typing import Optional

import pandas as pd

from models.url_filter_config import URLFilterConfig

logger = logging.getLogger(__name__)


class URLFilter:
    """Applies URL filtering to DataFrames and URL lists."""

    def __init__(self, config: Optional[URLFilterConfig] = None):
        self.config = config or URLFilterConfig()

    def should_include(self, url: str) -> bool:
        """Check if a URL should be included in analysis."""
        return self.config.should_include(url)

    def filter_urls(self, urls: list[str]) -> tuple[list[str], list[str]]:
        """Split URLs into included and excluded lists."""
        return self.config.filter_urls(urls)

    def filter_dataframe(
        self, df: pd.DataFrame, url_column: str = "page"
    ) -> pd.DataFrame:
        """Filter a DataFrame to only include SEO-relevant URLs.

        Args:
            df: DataFrame to filter.
            url_column: Name of the column containing URLs.

        Returns:
            Filtered DataFrame with only included URLs.
        """
        if df.empty or url_column not in df.columns:
            return df

        mask = df[url_column].apply(self.should_include)
        filtered = df[mask].reset_index(drop=True)

        excluded = len(df) - len(filtered)
        if excluded > 0:
            logger.info(
                f"URL filter: {len(filtered)} URLs included, "
                f"{excluded} excluded from {url_column} column"
            )

        return filtered

    def get_filter_preview(
        self, urls: list[str]
    ) -> dict:
        """Generate a preview of filter results for the UI.

        Returns a dict with counts and sample URLs for display.
        """
        included, excluded = self.filter_urls(urls)
        return {
            "total": len(urls),
            "included_count": len(included),
            "excluded_count": len(excluded),
            "included_sample": included[:20],
            "excluded_sample": excluded[:20],
            "inclusion_rate": (
                len(included) / len(urls) * 100 if urls else 0
            ),
        }
