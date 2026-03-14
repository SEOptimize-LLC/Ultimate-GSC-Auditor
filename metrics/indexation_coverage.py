"""Indexation & Coverage Health metrics (85-94).

Analyzes URL Inspection API data to evaluate soft 404s, redirect chains,
duplicate pollution, excluded URLs, server errors, robots blocks, noindex
usage, and crawl freshness across the inspected URL set.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from metrics.base_metric import BaseMetricGroup
from models.metric_result import MetricResult, Severity, TrendDirection

logger = logging.getLogger(__name__)


class IndexationCoverageMetrics(BaseMetricGroup):
    """Metrics 85-94: Indexation & Coverage Health analysis."""

    METRIC_REGISTRY: dict[int, str] = {
        85: "metric_soft_404_rate",
        86: "metric_redirect_chain_indexed_url_rate",
        87: "metric_alternate_page_suppression_rate",
        88: "metric_duplicate_url_index_pollution_rate",
        89: "metric_excluded_url_rate",
        90: "metric_server_error_crawl_rate",
        91: "metric_not_found_crawl_rate",
        92: "metric_robots_txt_block_rate",
        93: "metric_noindex_tag_rate",
        94: "metric_crawl_freshness_index",
    }

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _get_inspection_data(self) -> Optional[dict[str, dict]]:
        """Retrieve URL Inspection data from the store."""
        data = self.store.get("url_inspection")
        if data is None or not isinstance(data, dict) or len(data) == 0:
            return None
        return data

    def _get_index_status(self, result: dict) -> Optional[dict]:
        """Safely extract indexStatusResult from an inspection result.

        gsc_client.inspect_url() already returns the inner
        inspectionResult dict, so we access indexStatusResult directly.
        """
        return result.get("indexStatusResult")

    def _parse_crawl_time(self, time_str: str) -> Optional[datetime]:
        """Parse an ISO datetime string from the API into a timezone-aware datetime."""
        if not time_str:
            return None
        try:
            cleaned = time_str.replace("Z", "+00:00")
            return datetime.fromisoformat(cleaned)
        except (ValueError, TypeError):
            return None

    def _now_utc(self) -> datetime:
        """Return the current UTC time (timezone-aware)."""
        return datetime.now(timezone.utc)

    # ------------------------------------------------------------------ #
    # Metric 85 — Soft 404 Rate
    # ------------------------------------------------------------------ #
    def metric_soft_404_rate(self) -> MetricResult:
        """Percentage of URLs with pageFetchState 'SOFT_404'."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(85, "No URL Inspection data available")

        total = 0
        soft_404_count = 0
        affected_urls = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total += 1
            fetch_state = idx_status.get("pageFetchState", "")
            if fetch_state == "SOFT_404":
                soft_404_count += 1
                affected_urls.append({
                    "url": url,
                    "page_fetch_state": fetch_state,
                    "coverage_state": idx_status.get("coverageState", "Unknown"),
                    "verdict": idx_status.get("verdict", "Unknown"),
                })

        if total == 0:
            return self._error_result(85, "No valid inspection results found")

        rate = (soft_404_count / total * 100)

        if rate > 5:
            severity = Severity.HIGH
        elif rate > 2:
            severity = Severity.MEDIUM
        elif rate > 0:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        display_df = pd.DataFrame(affected_urls).head(25) if affected_urls else None

        summary = (
            f"{soft_404_count:,} of {total:,} inspected URLs ({rate:.1f}%) return "
            f"soft 404 responses. Soft 404s are pages that return a 200 status code "
            f"but Google detects them as error pages. These waste crawl budget and "
            f"dilute index quality."
        )

        recommendations = []
        if rate > 2:
            recommendations.extend([
                "Return proper 404 or 410 HTTP status codes for pages that no longer exist.",
                "Add meaningful content to thin pages that Google interprets as soft 404s.",
                "Redirect soft 404 URLs to relevant alternative pages if appropriate content exists.",
                "Check for empty or near-empty pages caused by template rendering issues or missing content.",
                "Review search/filter/pagination URLs that may generate empty result pages.",
            ])
        else:
            recommendations.append(
                "Soft 404 rate is low. Continue ensuring all pages serve meaningful content "
                "and return appropriate HTTP status codes."
            )

        return self.create_result(
            metric_id=85,
            severity=severity,
            summary=summary,
            computed_value=round(rate, 2),
            affected_count=soft_404_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_urls": total,
                "soft_404_count": soft_404_count,
                "soft_404_rate_pct": round(rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 86 — Redirect Chain Indexed URL Rate
    # ------------------------------------------------------------------ #
    def metric_redirect_chain_indexed_url_rate(self) -> MetricResult:
        """Percentage of URLs with coverageState containing 'redirect'."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(86, "No URL Inspection data available")

        total = 0
        redirect_count = 0
        affected_urls = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total += 1
            coverage_state = (idx_status.get("coverageState", "") or "").lower()
            if "redirect" in coverage_state:
                redirect_count += 1
                affected_urls.append({
                    "url": url,
                    "coverage_state": idx_status.get("coverageState", "Unknown"),
                    "verdict": idx_status.get("verdict", "Unknown"),
                    "indexing_state": idx_status.get("indexingState", "Unknown"),
                })

        if total == 0:
            return self._error_result(86, "No valid inspection results found")

        rate = (redirect_count / total * 100)

        if rate > 10:
            severity = Severity.MEDIUM
        elif rate > 5:
            severity = Severity.LOW
        elif rate > 0:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        display_df = pd.DataFrame(affected_urls).head(25) if affected_urls else None

        summary = (
            f"{redirect_count:,} of {total:,} inspected URLs ({rate:.1f}%) have a "
            f"coverage state involving redirects. Redirect chains waste crawl budget, "
            f"dilute link equity, and can cause indexing confusion when Google encounters "
            f"redirect loops or long chains."
        )

        recommendations = []
        if rate > 5:
            recommendations.extend([
                "Replace redirect chains with direct redirects to the final destination URL.",
                "Update internal links to point directly to canonical URLs instead of redirect sources.",
                "Audit redirect maps for chains (A->B->C) and collapse them to single hops (A->C).",
                "Remove redirect URLs from sitemaps — only include final destination URLs.",
                "Check for circular redirects or redirect loops that trap crawl budget.",
            ])
        else:
            recommendations.append(
                "Redirect chain rate is acceptable. Periodically audit redirects to prevent chain growth."
            )

        return self.create_result(
            metric_id=86,
            severity=severity,
            summary=summary,
            computed_value=round(rate, 2),
            affected_count=redirect_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_urls": total,
                "redirect_count": redirect_count,
                "redirect_rate_pct": round(rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 87 — Alternate Page Suppression Rate
    # ------------------------------------------------------------------ #
    def metric_alternate_page_suppression_rate(self) -> MetricResult:
        """Percentage of URLs with coverageState containing 'alternate' or 'duplicate'."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(87, "No URL Inspection data available")

        total = 0
        suppressed_count = 0
        affected_urls = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total += 1
            coverage_state = (idx_status.get("coverageState", "") or "").lower()
            if "alternate" in coverage_state or "duplicate" in coverage_state:
                suppressed_count += 1
                affected_urls.append({
                    "url": url,
                    "coverage_state": idx_status.get("coverageState", "Unknown"),
                    "verdict": idx_status.get("verdict", "Unknown"),
                    "indexing_state": idx_status.get("indexingState", "Unknown"),
                })

        if total == 0:
            return self._error_result(87, "No valid inspection results found")

        rate = (suppressed_count / total * 100)

        if rate > 20:
            severity = Severity.HIGH
        elif rate > 10:
            severity = Severity.MEDIUM
        elif rate > 5:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        display_df = pd.DataFrame(affected_urls).head(25) if affected_urls else None

        summary = (
            f"{suppressed_count:,} of {total:,} inspected URLs ({rate:.1f}%) are "
            f"suppressed as alternate or duplicate pages. Google has chosen a different "
            f"canonical URL for these pages, meaning they will not appear in search results. "
            f"High rates may indicate canonicalization issues or excessive URL duplication."
        )

        recommendations = []
        if rate > 10:
            recommendations.extend([
                "Review canonical tag implementation to ensure the correct preferred URL is specified.",
                "Identify URL parameter variations creating unnecessary duplicates and handle them via URL parameters in GSC.",
                "Consolidate duplicate content by redirecting non-canonical URLs to the preferred version.",
                "Check for hreflang issues causing alternate page suppression on multilingual sites.",
                "Verify that www/non-www and HTTP/HTTPS URL variants are properly consolidated.",
            ])
        else:
            recommendations.append(
                "Alternate page suppression is within normal range. Continue monitoring "
                "canonical tag accuracy and URL structure."
            )

        return self.create_result(
            metric_id=87,
            severity=severity,
            summary=summary,
            computed_value=round(rate, 2),
            affected_count=suppressed_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_urls": total,
                "suppressed_count": suppressed_count,
                "suppression_rate_pct": round(rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 88 — Duplicate URL Index Pollution Rate
    # ------------------------------------------------------------------ #
    def metric_duplicate_url_index_pollution_rate(self) -> MetricResult:
        """Duplicate-state URLs that are nonetheless indexed (verdict PASS)."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(88, "No URL Inspection data available")

        total_indexed = 0
        duplicate_indexed_count = 0
        affected_urls = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue

            verdict = idx_status.get("verdict", "")
            coverage_state = (idx_status.get("coverageState", "") or "").lower()

            if verdict == "PASS":
                total_indexed += 1
                if "duplicate" in coverage_state:
                    duplicate_indexed_count += 1
                    affected_urls.append({
                        "url": url,
                        "coverage_state": idx_status.get("coverageState", "Unknown"),
                        "verdict": verdict,
                        "indexing_state": idx_status.get("indexingState", "Unknown"),
                    })

        if total_indexed == 0:
            return self._error_result(88, "No indexed URLs found in inspection data")

        rate = (duplicate_indexed_count / total_indexed * 100)

        if rate > 15:
            severity = Severity.HIGH
        elif rate > 8:
            severity = Severity.MEDIUM
        elif rate > 3:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        display_df = pd.DataFrame(affected_urls).head(25) if affected_urls else None

        summary = (
            f"{duplicate_indexed_count:,} of {total_indexed:,} indexed URLs ({rate:.1f}%) "
            f"have a coverage state involving duplication yet remain indexed. This 'index "
            f"pollution' means Google is indexing multiple versions of the same content, "
            f"which splits ranking signals and can cause keyword cannibalization."
        )

        recommendations = []
        if rate > 3:
            recommendations.extend([
                "Implement or fix canonical tags on duplicate URLs to consolidate ranking signals to the preferred version.",
                "Set up 301 redirects from duplicate URLs to the canonical page where possible.",
                "Review URL structure for parameter-based duplicates and configure URL parameter handling in GSC.",
                "Add self-referencing canonical tags to all indexable pages as a defensive measure.",
                "Check CMS settings for generating duplicate URLs (trailing slashes, case sensitivity, session IDs).",
            ])
        else:
            recommendations.append(
                "Duplicate index pollution is minimal. Continue maintaining clean canonical "
                "signals and URL structure."
            )

        return self.create_result(
            metric_id=88,
            severity=severity,
            summary=summary,
            computed_value=round(rate, 2),
            affected_count=duplicate_indexed_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_indexed": total_indexed,
                "duplicate_indexed_count": duplicate_indexed_count,
                "pollution_rate_pct": round(rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 89 — Excluded URL Rate
    # ------------------------------------------------------------------ #
    def metric_excluded_url_rate(self) -> MetricResult:
        """Percentage of URLs with verdict FAIL or NEUTRAL (excluded from index)."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(89, "No URL Inspection data available")

        total = 0
        excluded_count = 0
        affected_urls = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total += 1
            verdict = idx_status.get("verdict", "")
            if verdict in ("FAIL", "NEUTRAL"):
                excluded_count += 1
                affected_urls.append({
                    "url": url,
                    "verdict": verdict,
                    "coverage_state": idx_status.get("coverageState", "Unknown"),
                    "page_fetch_state": idx_status.get("pageFetchState", "Unknown"),
                    "indexing_state": idx_status.get("indexingState", "Unknown"),
                })

        if total == 0:
            return self._error_result(89, "No valid inspection results found")

        rate = (excluded_count / total * 100)

        if rate > 30:
            severity = Severity.HIGH
        elif rate > 15:
            severity = Severity.MEDIUM
        elif rate > 5:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        # Sort by verdict to show FAILs first
        if affected_urls:
            affected_urls.sort(key=lambda x: (0 if x["verdict"] == "FAIL" else 1))
        display_df = pd.DataFrame(affected_urls).head(25) if affected_urls else None

        # Break down by verdict
        fail_count = sum(1 for u in affected_urls if u["verdict"] == "FAIL")
        neutral_count = sum(1 for u in affected_urls if u["verdict"] == "NEUTRAL")

        summary = (
            f"{excluded_count:,} of {total:,} inspected URLs ({rate:.1f}%) are excluded "
            f"from Google's index. {fail_count:,} URLs have FAIL verdicts (errors) and "
            f"{neutral_count:,} have NEUTRAL verdicts (intentional or quality-based exclusions). "
            f"Excluded URLs cannot appear in search results."
        )

        recommendations = []
        if rate > 15:
            recommendations.extend([
                "Categorize excluded URLs by coverage state to prioritize fixes — server errors need immediate attention.",
                "For FAIL verdicts: fix technical issues (server errors, blocked resources, bad redirects).",
                "For NEUTRAL verdicts: determine if exclusion is intentional (noindex) or a quality signal from Google.",
                "Remove excluded URLs from sitemaps to improve sitemap accuracy.",
                "Consolidate or redirect low-quality excluded pages to stronger content.",
            ])
        else:
            recommendations.append(
                "Excluded URL rate is within acceptable range. Monitor for increases "
                "that may signal new technical or quality issues."
            )

        return self.create_result(
            metric_id=89,
            severity=severity,
            summary=summary,
            computed_value=round(rate, 2),
            affected_count=excluded_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_urls": total,
                "excluded_count": excluded_count,
                "fail_count": fail_count,
                "neutral_count": neutral_count,
                "excluded_rate_pct": round(rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 90 — Server Error Crawl Rate
    # ------------------------------------------------------------------ #
    def metric_server_error_crawl_rate(self) -> MetricResult:
        """Percentage of URLs with pageFetchState 'SERVER_ERROR'."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(90, "No URL Inspection data available")

        total = 0
        error_count = 0
        affected_urls = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total += 1
            fetch_state = idx_status.get("pageFetchState", "")
            if fetch_state == "SERVER_ERROR":
                error_count += 1
                affected_urls.append({
                    "url": url,
                    "page_fetch_state": fetch_state,
                    "coverage_state": idx_status.get("coverageState", "Unknown"),
                    "verdict": idx_status.get("verdict", "Unknown"),
                    "last_crawl_time": idx_status.get("lastCrawlTime", "Unknown"),
                })

        if total == 0:
            return self._error_result(90, "No valid inspection results found")

        rate = (error_count / total * 100)

        if rate > 5:
            severity = Severity.CRITICAL
        elif rate > 2:
            severity = Severity.HIGH
        elif rate > 0:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        display_df = pd.DataFrame(affected_urls).head(25) if affected_urls else None

        summary = (
            f"{error_count:,} of {total:,} inspected URLs ({rate:.1f}%) returned server "
            f"errors (5xx) during Google's last crawl attempt. Server errors prevent "
            f"indexing and signal infrastructure instability to search engines. "
            f"{'This is a critical issue requiring immediate investigation.' if rate > 5 else ''}"
        )

        recommendations = []
        if rate > 0:
            recommendations.extend([
                "Investigate server logs for the affected URLs to identify the root cause of 5xx errors.",
                "Check server capacity and resource limits — spikes in Googlebot crawl rate can overload weak servers.",
                "Verify application errors are not causing specific URL patterns to return 500 responses.",
                "Monitor server uptime and set up alerts for recurring 5xx error spikes.",
                "After fixing, use the URL Inspection tool to request re-crawling of affected URLs.",
            ])
        else:
            recommendations.append(
                "No server errors detected during Google's crawl. Continue monitoring server health."
            )

        return self.create_result(
            metric_id=90,
            severity=severity,
            summary=summary,
            computed_value=round(rate, 2),
            affected_count=error_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_urls": total,
                "server_error_count": error_count,
                "server_error_rate_pct": round(rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 91 — Not-Found Crawl Rate
    # ------------------------------------------------------------------ #
    def metric_not_found_crawl_rate(self) -> MetricResult:
        """Percentage of URLs with pageFetchState 'NOT_FOUND'."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(91, "No URL Inspection data available")

        total = 0
        not_found_count = 0
        affected_urls = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total += 1
            fetch_state = idx_status.get("pageFetchState", "")
            if fetch_state == "NOT_FOUND":
                not_found_count += 1
                affected_urls.append({
                    "url": url,
                    "page_fetch_state": fetch_state,
                    "coverage_state": idx_status.get("coverageState", "Unknown"),
                    "verdict": idx_status.get("verdict", "Unknown"),
                })

        if total == 0:
            return self._error_result(91, "No valid inspection results found")

        rate = (not_found_count / total * 100)

        if rate > 10:
            severity = Severity.HIGH
        elif rate > 5:
            severity = Severity.MEDIUM
        elif rate > 0:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        display_df = pd.DataFrame(affected_urls).head(25) if affected_urls else None

        summary = (
            f"{not_found_count:,} of {total:,} inspected URLs ({rate:.1f}%) returned "
            f"404 (Not Found) during Google's crawl. Persistent 404 errors waste crawl "
            f"budget and can negatively impact user experience when linked from other pages "
            f"or search results."
        )

        recommendations = []
        if rate > 0:
            recommendations.extend([
                "Redirect deleted pages to relevant alternatives using 301 redirects to preserve link equity.",
                "Fix broken internal links pointing to 404 URLs — update or remove them.",
                "If pages were intentionally removed, consider returning 410 (Gone) to signal permanent removal.",
                "Audit external links pointing to 404 URLs and request link updates from referring sites.",
                "Remove 404 URLs from sitemaps to keep them clean and accurate.",
            ])
        else:
            recommendations.append(
                "No 404 errors detected during Google's crawl. Continue maintaining URL integrity."
            )

        return self.create_result(
            metric_id=91,
            severity=severity,
            summary=summary,
            computed_value=round(rate, 2),
            affected_count=not_found_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_urls": total,
                "not_found_count": not_found_count,
                "not_found_rate_pct": round(rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 92 — Robots.txt Block Rate
    # ------------------------------------------------------------------ #
    def metric_robots_txt_block_rate(self) -> MetricResult:
        """Percentage of URLs with robotsTxtState 'DISALLOWED'."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(92, "No URL Inspection data available")

        total = 0
        blocked_count = 0
        affected_urls = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total += 1
            robots_state = idx_status.get("robotsTxtState", "")
            if robots_state == "DISALLOWED":
                blocked_count += 1
                affected_urls.append({
                    "url": url,
                    "robots_txt_state": robots_state,
                    "coverage_state": idx_status.get("coverageState", "Unknown"),
                    "verdict": idx_status.get("verdict", "Unknown"),
                    "indexing_state": idx_status.get("indexingState", "Unknown"),
                })

        if total == 0:
            return self._error_result(92, "No valid inspection results found")

        rate = (blocked_count / total * 100)

        if rate > 10:
            severity = Severity.MEDIUM
        elif rate > 5:
            severity = Severity.LOW
        elif rate > 0:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        display_df = pd.DataFrame(affected_urls).head(25) if affected_urls else None

        summary = (
            f"{blocked_count:,} of {total:,} inspected URLs ({rate:.1f}%) are blocked "
            f"by robots.txt. Blocked URLs cannot be crawled or indexed by Google. "
            f"While some blocking is intentional (admin pages, staging), unintentional "
            f"blocks on important content prevent search visibility."
        )

        recommendations = []
        if rate > 5:
            recommendations.extend([
                "Audit robots.txt rules to ensure important content URLs are not accidentally blocked.",
                "Review broad disallow rules that may catch more URLs than intended (e.g., disallowing entire directories).",
                "Use the robots.txt Tester in Google Search Console to validate which URLs are affected.",
                "For intentionally blocked URLs, verify they are truly non-essential for search.",
                "Consider using noindex meta tags instead of robots.txt for pages that should not be indexed but may have links.",
            ])
        else:
            recommendations.append(
                "Robots.txt blocking is minimal. Ensure your robots.txt rules remain accurate "
                "as new URL patterns are added to the site."
            )

        return self.create_result(
            metric_id=92,
            severity=severity,
            summary=summary,
            computed_value=round(rate, 2),
            affected_count=blocked_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_urls": total,
                "blocked_count": blocked_count,
                "block_rate_pct": round(rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 93 — Noindex Tag Rate
    # ------------------------------------------------------------------ #
    def metric_noindex_tag_rate(self) -> MetricResult:
        """Percentage of URLs with indexingState containing 'BLOCKED'."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(93, "No URL Inspection data available")

        total = 0
        noindex_count = 0
        affected_urls = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total += 1
            indexing_state = (idx_status.get("indexingState", "") or "").upper()
            if "BLOCKED" in indexing_state:
                noindex_count += 1
                affected_urls.append({
                    "url": url,
                    "indexing_state": idx_status.get("indexingState", "Unknown"),
                    "coverage_state": idx_status.get("coverageState", "Unknown"),
                    "verdict": idx_status.get("verdict", "Unknown"),
                    "robots_txt_state": idx_status.get("robotsTxtState", "Unknown"),
                })

        if total == 0:
            return self._error_result(93, "No valid inspection results found")

        rate = (noindex_count / total * 100)

        if rate > 15:
            severity = Severity.MEDIUM
        elif rate > 8:
            severity = Severity.LOW
        elif rate > 0:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        display_df = pd.DataFrame(affected_urls).head(25) if affected_urls else None

        summary = (
            f"{noindex_count:,} of {total:,} inspected URLs ({rate:.1f}%) have their "
            f"indexing blocked by a noindex meta tag or X-Robots-Tag header. While noindex "
            f"is appropriate for admin, staging, and utility pages, having a high rate across "
            f"inspected URLs may indicate over-aggressive noindexing or misconfiguration."
        )

        recommendations = []
        if rate > 8:
            recommendations.extend([
                "Verify that noindexed URLs are intentionally excluded — accidental noindex tags on content pages cause traffic loss.",
                "Check CMS plugins or server configurations that may be applying noindex tags too broadly.",
                "Review if noindexed pages have inbound links — link equity is lost on noindexed pages.",
                "For pages that should be indexed, remove the noindex directive and request re-crawling.",
                "Document your noindex strategy to prevent accidental application during site changes.",
            ])
        else:
            recommendations.append(
                "Noindex usage is within normal range. Ensure new pages are not accidentally "
                "tagged with noindex during deployment."
            )

        return self.create_result(
            metric_id=93,
            severity=severity,
            summary=summary,
            computed_value=round(rate, 2),
            affected_count=noindex_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_urls": total,
                "noindex_count": noindex_count,
                "noindex_rate_pct": round(rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 94 — Crawl Freshness Index
    # ------------------------------------------------------------------ #
    def metric_crawl_freshness_index(self) -> MetricResult:
        """Average days since last crawl across all inspected URLs."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(94, "No URL Inspection data available")

        now = self._now_utc()
        url_ages = []
        urls_without_crawl = 0
        total_inspected = 0

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total_inspected += 1
            crawl_time_str = idx_status.get("lastCrawlTime", "")
            crawl_dt = self._parse_crawl_time(crawl_time_str)
            if crawl_dt is not None:
                days_since = (now - crawl_dt).days
                url_ages.append({
                    "url": url,
                    "last_crawl_time": crawl_time_str,
                    "days_since_crawl": days_since,
                })
            else:
                urls_without_crawl += 1

        if not url_ages:
            return self._error_result(94, "No URLs with crawl time data found")

        ages_df = pd.DataFrame(url_ages).sort_values(
            "days_since_crawl", ascending=False
        )

        avg_days = ages_df["days_since_crawl"].mean()
        median_days = ages_df["days_since_crawl"].median()
        max_days = ages_df["days_since_crawl"].max()
        min_days = ages_df["days_since_crawl"].min()

        # Distribution buckets
        within_7d = int((ages_df["days_since_crawl"] <= 7).sum())
        within_14d = int((ages_df["days_since_crawl"] <= 14).sum())
        within_30d = int((ages_df["days_since_crawl"] <= 30).sum())
        within_90d = int((ages_df["days_since_crawl"] <= 90).sum())
        over_90d = int((ages_df["days_since_crawl"] > 90).sum())

        if avg_days > 45:
            severity = Severity.HIGH
        elif avg_days > 21:
            severity = Severity.MEDIUM
        elif avg_days > 14:
            severity = Severity.LOW
        else:
            severity = Severity.INSIGHT

        if avg_days > 21:
            trend = TrendDirection.DECLINING
        else:
            trend = TrendDirection.STABLE

        # Show the stalest URLs
        display_df = ages_df[["url", "days_since_crawl", "last_crawl_time"]].head(25)

        summary = (
            f"Average crawl freshness: {avg_days:.1f} days since last crawl "
            f"(median: {median_days:.0f} days) across {len(url_ages):,} URLs with crawl data. "
            f"Range: {min_days:,}-{max_days:,} days. "
            f"Distribution: {within_7d:,} within 7d, {within_30d:,} within 30d, "
            f"{over_90d:,} over 90d. "
            f"{urls_without_crawl:,} URLs have no recorded crawl time. "
            f"{'Stale crawl freshness suggests Google is not prioritizing re-crawling your content.' if avg_days > 21 else 'Crawl freshness is healthy across the site.'}"
        )

        recommendations = []
        if avg_days > 21:
            recommendations.extend([
                "Update content regularly to signal freshness to Google and encourage more frequent crawling.",
                "Improve internal linking to stale pages from frequently crawled sections of the site.",
                "Submit updated XML sitemaps with accurate lastmod dates to guide Googlebot priority.",
                "Reduce server response times to allow Googlebot to crawl more pages per session.",
                "Prune or consolidate low-value pages to focus crawl budget on important content.",
            ])
        else:
            recommendations.append(
                "Crawl freshness is healthy. Continue publishing fresh content and maintaining "
                "strong internal linking to keep Googlebot returning frequently."
            )

        return self.create_result(
            metric_id=94,
            severity=severity,
            summary=summary,
            computed_value=round(avg_days, 2),
            affected_count=over_90d + urls_without_crawl,
            data_table=display_df,
            recommendations=recommendations,
            trend_direction=trend,
            details={
                "avg_days_since_crawl": round(avg_days, 2),
                "median_days_since_crawl": round(float(median_days), 2),
                "max_days_since_crawl": int(max_days),
                "min_days_since_crawl": int(min_days),
                "total_with_crawl_data": len(url_ages),
                "urls_without_crawl_data": urls_without_crawl,
                "total_inspected": total_inspected,
                "within_7d": within_7d,
                "within_14d": within_14d,
                "within_30d": within_30d,
                "within_90d": within_90d,
                "over_90d": over_90d,
            },
        )
