"""Google Search Console API client with OAuth 2.0 authentication."""

import logging
import time
import urllib.parse
from typing import Any, Optional

import pandas as pd
import requests as http_requests
import streamlit as st
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]
API_SERVICE_NAME = "searchconsole"
API_VERSION = "v1"
MAX_ROWS_PER_REQUEST = 25_000

_GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _get_redirect_uri() -> str:
    return st.secrets.get(
        "GOOGLE_REDIRECT_URI", "http://localhost:8501"
    )


def get_authorization_url() -> str:
    """Build Google OAuth authorization URL manually (no PKCE)."""
    params = {
        "client_id": st.secrets["GOOGLE_CLIENT_ID"],
        "redirect_uri": _get_redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{_GOOGLE_AUTH_URI}?{urllib.parse.urlencode(params)}"


def handle_oauth_callback(auth_code: str) -> Credentials:
    """Exchange the authorization code for credentials via direct HTTP."""
    resp = http_requests.post(
        _GOOGLE_TOKEN_URI,
        data={
            "client_id": st.secrets["GOOGLE_CLIENT_ID"],
            "client_secret": st.secrets["GOOGLE_CLIENT_SECRET"],
            "code": auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": _get_redirect_uri(),
        },
    )
    token_data = resp.json()
    if "error" in token_data:
        raise Exception(
            f"({token_data['error']}) "
            f"{token_data.get('error_description', '')}"
        )
    return Credentials(
        token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_uri=_GOOGLE_TOKEN_URI,
        client_id=st.secrets["GOOGLE_CLIENT_ID"],
        client_secret=st.secrets["GOOGLE_CLIENT_SECRET"],
        scopes=SCOPES,
    )


class GSCClient:
    """Wrapper around the Google Search Console API."""

    def __init__(self, credentials: Credentials):
        self.credentials = credentials
        self.service = build(
            API_SERVICE_NAME,
            API_VERSION,
            credentials=credentials,
            cache_discovery=False,
        )

    def list_properties(self) -> list[dict[str, str]]:
        """List all verified GSC properties."""
        response = self.service.sites().list().execute()
        sites = response.get("siteEntry", [])
        return [
            {
                "url": site["siteUrl"],
                "permission": site.get("permissionLevel", "unknown"),
            }
            for site in sites
        ]

    def query_search_analytics(
        self,
        site_url: str,
        start_date: str,
        end_date: str,
        dimensions: list[str],
        search_type: str = "web",
        row_limit: int = MAX_ROWS_PER_REQUEST,
        start_row: int = 0,
        dimension_filter_groups: Optional[list[dict]] = None,
    ) -> list[dict[str, Any]]:
        """Execute a single Search Analytics query."""
        body: dict[str, Any] = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": dimensions,
            "type": search_type,
            "rowLimit": row_limit,
            "startRow": start_row,
        }
        if dimension_filter_groups:
            body["dimensionFilterGroups"] = dimension_filter_groups

        response = (
            self.service.searchanalytics()
            .query(siteUrl=site_url, body=body)
            .execute()
        )
        return response.get("rows", [])

    def query_search_analytics_all(
        self,
        site_url: str,
        start_date: str,
        end_date: str,
        dimensions: list[str],
        search_type: str = "web",
    ) -> pd.DataFrame:
        """Fetch all Search Analytics data with automatic pagination."""
        all_rows: list[dict[str, Any]] = []
        start_row = 0

        while True:
            rows = self.query_search_analytics(
                site_url=site_url,
                start_date=start_date,
                end_date=end_date,
                dimensions=dimensions,
                search_type=search_type,
                row_limit=MAX_ROWS_PER_REQUEST,
                start_row=start_row,
            )
            if not rows:
                break

            all_rows.extend(rows)
            if len(rows) < MAX_ROWS_PER_REQUEST:
                break
            start_row += MAX_ROWS_PER_REQUEST

        return self._rows_to_dataframe(all_rows, dimensions)

    def query_search_analytics_by_type(
        self,
        site_url: str,
        start_date: str,
        end_date: str,
        dimensions: list[str],
        search_type: str,
    ) -> pd.DataFrame:
        """Fetch Search Analytics data for a specific search type (discover, news, image, video, web)."""
        return self.query_search_analytics_all(
            site_url=site_url,
            start_date=start_date,
            end_date=end_date,
            dimensions=dimensions,
            search_type=search_type,
        )

    def inspect_url(
        self, site_url: str, page_url: str
    ) -> dict[str, Any]:
        """Inspect a single URL for indexing status."""
        body = {
            "inspectionUrl": page_url,
            "siteUrl": site_url,
        }
        response = (
            self.service.urlInspection()
            .index()
            .inspect(body=body)
            .execute()
        )
        return response.get("inspectionResult", {})

    def inspect_urls_batch(
        self,
        site_url: str,
        urls: list[str],
        progress_callback=None,
        delay_seconds: float = 0.5,
    ) -> dict[str, dict[str, Any]]:
        """Inspect multiple URLs with rate limiting.

        Returns a dict mapping each URL to its inspection result.
        Uses delay between requests to respect API rate limits.
        """
        results: dict[str, dict[str, Any]] = {}
        total = len(urls)

        for i, url in enumerate(urls):
            try:
                result = self.inspect_url(site_url, url)
                results[url] = result
            except Exception as e:
                logger.warning(f"URL inspection failed for {url}: {e}")
                results[url] = {"error": str(e)}

            if progress_callback:
                progress_callback(i + 1, total)

            if i < total - 1:
                time.sleep(delay_seconds)

        return results

    def list_sitemaps(self, site_url: str) -> list[dict[str, Any]]:
        """List all sitemaps for a property."""
        response = self.service.sitemaps().list(siteUrl=site_url).execute()
        return response.get("sitemap", [])

    def get_sitemap(self, site_url: str, sitemap_url: str) -> dict[str, Any]:
        """Get details for a specific sitemap."""
        return (
            self.service.sitemaps()
            .get(siteUrl=site_url, feedpath=sitemap_url)
            .execute()
        )

    @staticmethod
    def _rows_to_dataframe(
        rows: list[dict[str, Any]], dimensions: list[str]
    ) -> pd.DataFrame:
        """Convert GSC API response rows into a pandas DataFrame."""
        if not rows:
            return pd.DataFrame(
                columns=dimensions + ["clicks", "impressions", "ctr", "position"]
            )

        records = []
        for row in rows:
            record = {}
            keys = row.get("keys", [])
            for i, dim in enumerate(dimensions):
                record[dim] = keys[i] if i < len(keys) else None
            record["clicks"] = row.get("clicks", 0)
            record["impressions"] = row.get("impressions", 0)
            record["ctr"] = row.get("ctr", 0.0)
            record["position"] = row.get("position", 0.0)
            records.append(record)

        df = pd.DataFrame(records)
        df["clicks"] = df["clicks"].astype(int)
        df["impressions"] = df["impressions"].astype(int)
        df["ctr"] = df["ctr"].astype(float)
        df["position"] = df["position"].astype(float)
        return df
