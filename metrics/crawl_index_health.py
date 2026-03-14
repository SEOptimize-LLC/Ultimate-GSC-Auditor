"""Crawl & Index Health metrics (35-44).

Analyzes URL Inspection API data to evaluate crawl rates, index coverage,
crawl budget efficiency, and sitemap-sourced indexing. These metrics help
identify crawl bottlenecks, unindexed content, and wasted crawl budget.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from metrics.base_metric import BaseMetricGroup
from models.metric_result import MetricResult, Severity, TrendDirection

logger = logging.getLogger(__name__)


class CrawlIndexHealthMetrics(BaseMetricGroup):
    """Metrics 35-44: Crawl & Index Health analysis."""

    METRIC_REGISTRY: dict[int, str] = {
        35: "metric_url_crawl_rate_30d",
        36: "metric_url_crawl_rate_90d",
        37: "metric_crawl_frequency_per_url",
        38: "metric_days_since_last_crawl",
        39: "metric_discovered_not_crawled_rate",
        40: "metric_crawled_not_indexed_rate",
        41: "metric_indexed_url_coverage_rate",
        42: "metric_coverage_error_rate",
        43: "metric_crawl_budget_efficiency_ratio",
        44: "metric_sitemap_sourced_index_rate",
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
            # Handle trailing 'Z' and various ISO formats
            cleaned = time_str.replace("Z", "+00:00")
            return datetime.fromisoformat(cleaned)
        except (ValueError, TypeError):
            return None

    def _now_utc(self) -> datetime:
        """Return the current UTC time (timezone-aware)."""
        return datetime.now(timezone.utc)

    # ------------------------------------------------------------------ #
    # Metric 35 — URL Crawl Rate (Last 30 Days)
    # ------------------------------------------------------------------ #
    def metric_url_crawl_rate_30d(self) -> MetricResult:
        """Percentage of inspected URLs crawled within the last 30 days."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(35, "No URL Inspection data available")

        now = self._now_utc()
        cutoff_30d = now - timedelta(days=30)
        total = 0
        crawled_30d = 0
        url_details = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total += 1
            crawl_time_str = idx_status.get("lastCrawlTime", "")
            crawl_dt = self._parse_crawl_time(crawl_time_str)
            was_crawled = crawl_dt is not None and crawl_dt >= cutoff_30d
            if was_crawled:
                crawled_30d += 1
            url_details.append({
                "url": url,
                "last_crawl_time": crawl_time_str or "Never",
                "crawled_within_30d": was_crawled,
            })

        if total == 0:
            return self._error_result(35, "No valid inspection results found")

        crawl_rate = crawled_30d / total * 100
        not_crawled = total - crawled_30d

        if crawl_rate < 50:
            severity = Severity.HIGH
        elif crawl_rate < 70:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        # Show URLs NOT crawled recently (most concerning)
        not_crawled_urls = [u for u in url_details if not u["crawled_within_30d"]]
        display_df = pd.DataFrame(not_crawled_urls).head(25) if not_crawled_urls else None

        summary = (
            f"{crawled_30d:,} of {total:,} inspected URLs ({crawl_rate:.1f}%) were "
            f"crawled in the last 30 days. {not_crawled:,} URLs have not been "
            f"recently crawled, which may indicate crawl budget or accessibility issues."
        )

        recommendations = []
        if crawl_rate < 70:
            recommendations.extend([
                "Improve internal linking to stale pages so Googlebot discovers them more frequently.",
                "Submit updated sitemaps to encourage crawling of neglected URLs.",
                "Check server response times — slow responses can cause Googlebot to reduce crawl rate.",
                "Remove or noindex low-value pages to free crawl budget for important content.",
            ])
        else:
            recommendations.append(
                "Crawl rate is healthy. Continue monitoring for any URLs that stop being crawled."
            )

        return self.create_result(
            metric_id=35,
            severity=severity,
            summary=summary,
            computed_value=round(crawl_rate, 2),
            affected_count=not_crawled,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_urls": total,
                "crawled_30d": crawled_30d,
                "not_crawled_30d": not_crawled,
                "crawl_rate_pct": round(crawl_rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 36 — URL Crawl Rate (Last 90 Days)
    # ------------------------------------------------------------------ #
    def metric_url_crawl_rate_90d(self) -> MetricResult:
        """Percentage of inspected URLs crawled within the last 90 days."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(36, "No URL Inspection data available")

        now = self._now_utc()
        cutoff_90d = now - timedelta(days=90)
        total = 0
        crawled_90d = 0
        url_details = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total += 1
            crawl_time_str = idx_status.get("lastCrawlTime", "")
            crawl_dt = self._parse_crawl_time(crawl_time_str)
            was_crawled = crawl_dt is not None and crawl_dt >= cutoff_90d
            if was_crawled:
                crawled_90d += 1
            url_details.append({
                "url": url,
                "last_crawl_time": crawl_time_str or "Never",
                "crawled_within_90d": was_crawled,
            })

        if total == 0:
            return self._error_result(36, "No valid inspection results found")

        crawl_rate = crawled_90d / total * 100
        not_crawled = total - crawled_90d

        if crawl_rate < 50:
            severity = Severity.CRITICAL
        elif crawl_rate < 70:
            severity = Severity.HIGH
        else:
            severity = Severity.INSIGHT

        not_crawled_urls = [u for u in url_details if not u["crawled_within_90d"]]
        display_df = pd.DataFrame(not_crawled_urls).head(25) if not_crawled_urls else None

        summary = (
            f"{crawled_90d:,} of {total:,} inspected URLs ({crawl_rate:.1f}%) were "
            f"crawled in the last 90 days. {not_crawled:,} URLs have gone over "
            f"3 months without a crawl, suggesting potential orphan pages or crawl issues."
        )

        recommendations = []
        if crawl_rate < 70:
            recommendations.extend([
                "Audit uncrawled URLs for orphan page issues — they may lack internal links.",
                "Verify server health and robots.txt rules are not blocking Googlebot.",
                "Consolidate or prune content that Google has abandoned crawling.",
                "Consider requesting indexing for important URLs via Search Console.",
            ])
        else:
            recommendations.append(
                "90-day crawl coverage is healthy. Monitor for URLs that drift into stale territory."
            )

        return self.create_result(
            metric_id=36,
            severity=severity,
            summary=summary,
            computed_value=round(crawl_rate, 2),
            affected_count=not_crawled,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_urls": total,
                "crawled_90d": crawled_90d,
                "not_crawled_90d": not_crawled,
                "crawl_rate_pct": round(crawl_rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 37 — Crawl Frequency per URL
    # ------------------------------------------------------------------ #
    def metric_crawl_frequency_per_url(self) -> MetricResult:
        """Average days since last crawl across all URLs with crawl data."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(37, "No URL Inspection data available")

        now = self._now_utc()
        url_ages = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            crawl_time_str = idx_status.get("lastCrawlTime", "")
            crawl_dt = self._parse_crawl_time(crawl_time_str)
            if crawl_dt is not None:
                days_since = (now - crawl_dt).days
                url_ages.append({
                    "url": url,
                    "last_crawl_time": crawl_time_str,
                    "days_since_crawl": days_since,
                })

        if not url_ages:
            return self._error_result(37, "No URLs with crawl time data found")

        ages_df = pd.DataFrame(url_ages).sort_values("days_since_crawl", ascending=False)
        avg_days = ages_df["days_since_crawl"].mean()
        median_days = ages_df["days_since_crawl"].median()
        total_crawled = len(ages_df)

        # Distribution buckets
        within_7d = len(ages_df[ages_df["days_since_crawl"] <= 7])
        within_14d = len(ages_df[ages_df["days_since_crawl"] <= 14])
        within_30d = len(ages_df[ages_df["days_since_crawl"] <= 30])
        within_90d = len(ages_df[ages_df["days_since_crawl"] <= 90])
        over_90d = len(ages_df[ages_df["days_since_crawl"] > 90])

        if avg_days > 30:
            severity = Severity.HIGH
        elif avg_days > 14:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        display_df = ages_df[["url", "days_since_crawl"]].head(25)

        summary = (
            f"Average days since last crawl: {avg_days:.1f} (median: {median_days:.0f}) "
            f"across {total_crawled:,} URLs. Distribution: {within_7d:,} within 7 days, "
            f"{within_30d:,} within 30 days, {over_90d:,} over 90 days."
        )

        recommendations = []
        if avg_days > 14:
            recommendations.extend([
                "Improve crawl frequency by updating content regularly — fresh content signals encourage re-crawling.",
                "Strengthen internal linking to pages with infrequent crawls.",
                "Reduce page load times to allow Googlebot to crawl more pages per session.",
                "Submit an updated XML sitemap with lastmod dates to guide crawl priority.",
            ])
        else:
            recommendations.append(
                "Crawl frequency is healthy. Continue maintaining fresh content and strong internal linking."
            )

        return self.create_result(
            metric_id=37,
            severity=severity,
            summary=summary,
            computed_value=round(avg_days, 2),
            affected_count=over_90d,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "average_days_since_crawl": round(avg_days, 2),
                "median_days_since_crawl": round(median_days, 2),
                "total_crawled_urls": total_crawled,
                "within_7d": within_7d,
                "within_14d": within_14d,
                "within_30d": within_30d,
                "within_90d": within_90d,
                "over_90d": over_90d,
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 38 — Days Since Last Crawl
    # ------------------------------------------------------------------ #
    def metric_days_since_last_crawl(self) -> MetricResult:
        """Identify URLs with the longest time since their last crawl."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(38, "No URL Inspection data available")

        now = self._now_utc()
        url_ages = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
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
                # URLs with no crawl time are effectively never-crawled
                url_ages.append({
                    "url": url,
                    "last_crawl_time": "Never",
                    "days_since_crawl": -1,  # sentinel for never-crawled
                })

        if not url_ages:
            return self._error_result(38, "No valid inspection results found")

        ages_df = pd.DataFrame(url_ages)

        # Separate never-crawled from aged URLs
        never_crawled = ages_df[ages_df["days_since_crawl"] == -1]
        crawled_df = ages_df[ages_df["days_since_crawl"] >= 0].sort_values(
            "days_since_crawl", ascending=False
        )

        max_days = crawled_df["days_since_crawl"].max() if not crawled_df.empty else 0
        over_90d = len(crawled_df[crawled_df["days_since_crawl"] > 90])
        over_60d = len(crawled_df[crawled_df["days_since_crawl"] > 60])
        never_count = len(never_crawled)

        stale_count = over_90d + never_count

        if over_90d > 0 or never_count > 0:
            severity = Severity.HIGH
        elif over_60d > 0:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        # Show the stalest URLs first (never-crawled + oldest)
        display_parts = []
        if not never_crawled.empty:
            nc_display = never_crawled.copy()
            nc_display["days_since_crawl"] = "Never"
            display_parts.append(nc_display)
        if not crawled_df.empty:
            display_parts.append(crawled_df)

        display_df = pd.concat(display_parts, ignore_index=True).head(25) if display_parts else None

        summary = (
            f"Stalest crawl: {max_days:,} days ago. {over_90d:,} URLs not crawled in 90+ days, "
            f"{over_60d:,} in 60+ days. {never_count:,} URLs have no recorded crawl time. "
            f"Stale URLs risk falling out of Google's index."
        )

        recommendations = []
        if stale_count > 0:
            recommendations.extend([
                "Prioritize updating and re-submitting stale URLs through Search Console.",
                "Add internal links from frequently crawled pages to stale content.",
                "Check if stale pages return proper HTTP status codes (200, not soft 404).",
                "Consider whether very stale pages should be consolidated, redirected, or removed.",
            ])
        else:
            recommendations.append(
                "All URLs have been crawled recently. Maintain good content freshness practices."
            )

        return self.create_result(
            metric_id=38,
            severity=severity,
            summary=summary,
            computed_value=float(max_days),
            affected_count=stale_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "max_days_since_crawl": max_days,
                "over_90d_count": over_90d,
                "over_60d_count": over_60d,
                "never_crawled_count": never_count,
                "total_urls": len(ages_df),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 39 — Discovered-but-Not-Crawled Rate
    # ------------------------------------------------------------------ #
    def metric_discovered_not_crawled_rate(self) -> MetricResult:
        """Percentage of URLs with 'Discovered - currently not indexed' status."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(39, "No URL Inspection data available")

        total = 0
        discovered_not_crawled = 0
        affected_urls = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total += 1
            coverage_state = idx_status.get("coverageState", "")
            if coverage_state == "Discovered - currently not indexed":
                discovered_not_crawled += 1
                affected_urls.append({
                    "url": url,
                    "coverage_state": coverage_state,
                    "robots_txt": idx_status.get("robotsTxtState", "Unknown"),
                })

        if total == 0:
            return self._error_result(39, "No valid inspection results found")

        rate = discovered_not_crawled / total * 100

        if rate > 30:
            severity = Severity.CRITICAL
        elif rate > 15:
            severity = Severity.HIGH
        else:
            severity = Severity.INSIGHT

        display_df = pd.DataFrame(affected_urls).head(25) if affected_urls else None

        summary = (
            f"{discovered_not_crawled:,} of {total:,} URLs ({rate:.1f}%) are in "
            f"'Discovered - currently not indexed' state. Google knows these URLs "
            f"exist but has not crawled them, often due to crawl budget constraints "
            f"or low perceived value."
        )

        recommendations = []
        if rate > 15:
            recommendations.extend([
                "Improve the quality signals of discovered pages — add unique, valuable content.",
                "Boost internal linking to these pages from authoritative sections of your site.",
                "Reduce total URL count by pruning thin or duplicate pages to free crawl budget.",
                "Ensure server response times are fast to maximize Googlebot's crawl efficiency.",
                "Submit these URLs through the Search Console URL Inspection tool.",
            ])
        else:
            recommendations.append(
                "Discovered-but-not-crawled rate is within acceptable range. Monitor for increases."
            )

        return self.create_result(
            metric_id=39,
            severity=severity,
            summary=summary,
            computed_value=round(rate, 2),
            affected_count=discovered_not_crawled,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_urls": total,
                "discovered_not_crawled": discovered_not_crawled,
                "rate_pct": round(rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 40 — Crawled-but-Not-Indexed Rate
    # ------------------------------------------------------------------ #
    def metric_crawled_not_indexed_rate(self) -> MetricResult:
        """Percentage of URLs with 'Crawled - currently not indexed' status."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(40, "No URL Inspection data available")

        total = 0
        crawled_not_indexed = 0
        affected_urls = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total += 1
            coverage_state = idx_status.get("coverageState", "")
            if coverage_state == "Crawled - currently not indexed":
                crawled_not_indexed += 1
                affected_urls.append({
                    "url": url,
                    "coverage_state": coverage_state,
                    "page_fetch_state": idx_status.get("pageFetchState", "Unknown"),
                    "last_crawl_time": idx_status.get("lastCrawlTime", "Unknown"),
                })

        if total == 0:
            return self._error_result(40, "No valid inspection results found")

        rate = crawled_not_indexed / total * 100

        if rate > 30:
            severity = Severity.CRITICAL
        elif rate > 15:
            severity = Severity.HIGH
        else:
            severity = Severity.INSIGHT

        display_df = pd.DataFrame(affected_urls).head(25) if affected_urls else None

        summary = (
            f"{crawled_not_indexed:,} of {total:,} URLs ({rate:.1f}%) are in "
            f"'Crawled - currently not indexed' state. Google crawled these pages "
            f"but chose not to index them, typically due to low quality, thin content, "
            f"or duplication."
        )

        recommendations = []
        if rate > 15:
            recommendations.extend([
                "Audit affected pages for thin content — add substantial, unique value.",
                "Check for near-duplicate content across affected URLs and consolidate with canonical tags.",
                "Ensure pages have clear E-E-A-T signals (expertise, experience, authoritativeness, trust).",
                "Review whether affected URLs should be noindexed intentionally or redirected.",
                "Improve page quality with structured data, multimedia, and comprehensive coverage.",
            ])
        else:
            recommendations.append(
                "Crawled-but-not-indexed rate is acceptable. Continue improving content quality."
            )

        return self.create_result(
            metric_id=40,
            severity=severity,
            summary=summary,
            computed_value=round(rate, 2),
            affected_count=crawled_not_indexed,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_urls": total,
                "crawled_not_indexed": crawled_not_indexed,
                "rate_pct": round(rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 41 — Indexed URL Coverage Rate
    # ------------------------------------------------------------------ #
    def metric_indexed_url_coverage_rate(self) -> MetricResult:
        """Percentage of inspected URLs that are indexed (verdict PASS)."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(41, "No URL Inspection data available")

        total = 0
        indexed = 0
        not_indexed_urls = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total += 1
            verdict = idx_status.get("verdict", "")
            if verdict == "PASS":
                indexed += 1
            else:
                not_indexed_urls.append({
                    "url": url,
                    "verdict": verdict,
                    "coverage_state": idx_status.get("coverageState", "Unknown"),
                    "indexing_state": idx_status.get("indexingState", "Unknown"),
                })

        if total == 0:
            return self._error_result(41, "No valid inspection results found")

        coverage_rate = indexed / total * 100
        not_indexed_count = total - indexed

        if coverage_rate < 50:
            severity = Severity.CRITICAL
        elif coverage_rate < 70:
            severity = Severity.HIGH
        elif coverage_rate < 85:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        # Sort not-indexed URLs for display
        display_df = (
            pd.DataFrame(not_indexed_urls)
            .sort_values("verdict", ascending=True)
            .head(25)
            if not_indexed_urls else None
        )

        summary = (
            f"{indexed:,} of {total:,} inspected URLs ({coverage_rate:.1f}%) are "
            f"indexed by Google. {not_indexed_count:,} URLs are not indexed, which "
            f"means they cannot appear in search results."
        )

        recommendations = []
        if coverage_rate < 85:
            recommendations.extend([
                "Investigate why unindexed URLs are being excluded — check coverage state for specific reasons.",
                "Ensure important pages are not blocked by robots.txt, noindex tags, or canonical issues.",
                "Improve content quality on unindexed pages to meet Google's indexing threshold.",
                "Submit important unindexed URLs for indexing via the URL Inspection tool.",
                "Consider whether unindexed pages should be pruned, redirected, or consolidated.",
            ])
        else:
            recommendations.append(
                "Index coverage is strong. Monitor for any drops in indexed URL count over time."
            )

        return self.create_result(
            metric_id=41,
            severity=severity,
            summary=summary,
            computed_value=round(coverage_rate, 2),
            affected_count=not_indexed_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_urls": total,
                "indexed_urls": indexed,
                "not_indexed_urls": not_indexed_count,
                "coverage_rate_pct": round(coverage_rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 42 — Coverage Error Rate
    # ------------------------------------------------------------------ #
    def metric_coverage_error_rate(self) -> MetricResult:
        """Percentage of URLs where the inspection verdict is FAIL."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(42, "No URL Inspection data available")

        total = 0
        fail_count = 0
        failed_urls = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            total += 1
            verdict = idx_status.get("verdict", "")
            if verdict == "FAIL":
                fail_count += 1
                failed_urls.append({
                    "url": url,
                    "coverage_state": idx_status.get("coverageState", "Unknown"),
                    "page_fetch_state": idx_status.get("pageFetchState", "Unknown"),
                    "robots_txt": idx_status.get("robotsTxtState", "Unknown"),
                    "indexing_state": idx_status.get("indexingState", "Unknown"),
                })

        if total == 0:
            return self._error_result(42, "No valid inspection results found")

        error_rate = fail_count / total * 100

        if error_rate > 20:
            severity = Severity.CRITICAL
        elif error_rate > 10:
            severity = Severity.HIGH
        else:
            severity = Severity.INSIGHT

        display_df = pd.DataFrame(failed_urls).head(25) if failed_urls else None

        summary = (
            f"{fail_count:,} of {total:,} URLs ({error_rate:.1f}%) have a FAIL "
            f"verdict in URL inspection. These URLs have coverage errors preventing "
            f"them from appearing in search results."
        )

        recommendations = []
        if error_rate > 10:
            recommendations.extend([
                "Investigate each failed URL's coverage state to identify the root cause (server errors, redirects, blocks).",
                "Fix server errors (5xx) immediately — they indicate infrastructure problems.",
                "Resolve 404 errors by either restoring content or implementing proper redirects.",
                "Remove unintentional robots.txt blocks or noindex directives on important pages.",
                "After fixes, use the URL Inspection tool to request re-crawling and validate.",
            ])
        else:
            recommendations.append(
                "Coverage error rate is low. Periodically review failed URLs to catch new issues early."
            )

        return self.create_result(
            metric_id=42,
            severity=severity,
            summary=summary,
            computed_value=round(error_rate, 2),
            affected_count=fail_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_urls": total,
                "fail_count": fail_count,
                "error_rate_pct": round(error_rate, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 43 — Crawl Budget Efficiency Ratio
    # ------------------------------------------------------------------ #
    def metric_crawl_budget_efficiency_ratio(self) -> MetricResult:
        """Of crawled URLs, what percentage also generate impressions in GSC."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(43, "No URL Inspection data available")

        page_df = self.get_df("page_90d")
        if page_df.empty:
            return self._error_result(43, "No page-level performance data available")

        # Collect URLs that have a lastCrawlTime (i.e., were crawled)
        crawled_urls = set()
        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue
            crawl_time_str = idx_status.get("lastCrawlTime", "")
            if crawl_time_str:
                crawled_urls.add(url)

        if not crawled_urls:
            return self._error_result(43, "No crawled URLs found in inspection data")

        # URLs with impressions from page_90d
        impression_urls = set(page_df[page_df["impressions"] > 0]["page"].unique())

        # Crawled URLs that also have impressions
        efficient_urls = crawled_urls & impression_urls
        wasted_urls = crawled_urls - impression_urls

        total_crawled = len(crawled_urls)
        efficient_count = len(efficient_urls)
        wasted_count = len(wasted_urls)
        efficiency_ratio = efficient_count / total_crawled * 100

        if efficiency_ratio < 50:
            severity = Severity.HIGH
        elif efficiency_ratio < 70:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        # Show wasted crawl budget URLs
        wasted_details = []
        for url in sorted(wasted_urls):
            idx_status = self._get_index_status(inspection_data[url])
            wasted_details.append({
                "url": url,
                "coverage_state": idx_status.get("coverageState", "Unknown") if idx_status else "Unknown",
                "last_crawl_time": idx_status.get("lastCrawlTime", "Unknown") if idx_status else "Unknown",
            })

        display_df = pd.DataFrame(wasted_details).head(25) if wasted_details else None

        summary = (
            f"{efficient_count:,} of {total_crawled:,} crawled URLs ({efficiency_ratio:.1f}%) "
            f"also generate search impressions. {wasted_count:,} URLs consume crawl budget "
            f"without contributing to search visibility."
        )

        recommendations = []
        if efficiency_ratio < 70:
            recommendations.extend([
                "Identify and noindex or remove low-value pages that consume crawl budget without generating traffic.",
                "Consolidate thin or redundant pages into comprehensive resources.",
                "Block crawling of utility pages (pagination, tag pages, filtered views) via robots.txt if they add no search value.",
                "Focus crawl budget on high-value content by improving internal linking hierarchy.",
                "Review faceted navigation and URL parameters that may create crawlable but valueless URLs.",
            ])
        else:
            recommendations.append(
                "Crawl budget efficiency is healthy. Most crawled pages contribute to search visibility."
            )

        return self.create_result(
            metric_id=43,
            severity=severity,
            summary=summary,
            computed_value=round(efficiency_ratio, 2),
            affected_count=wasted_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_crawled": total_crawled,
                "efficient_urls": efficient_count,
                "wasted_urls": wasted_count,
                "efficiency_ratio_pct": round(efficiency_ratio, 2),
            },
        )

    # ------------------------------------------------------------------ #
    # Metric 44 — Sitemap-Sourced Index Rate
    # ------------------------------------------------------------------ #
    def metric_sitemap_sourced_index_rate(self) -> MetricResult:
        """Of URLs listed in a sitemap, what percentage are indexed."""
        inspection_data = self._get_inspection_data()
        if inspection_data is None:
            return self._error_result(44, "No URL Inspection data available")

        total_with_sitemap = 0
        indexed_with_sitemap = 0
        not_indexed_sitemap_urls = []

        for url, result in inspection_data.items():
            idx_status = self._get_index_status(result)
            if idx_status is None:
                continue

            # Check if URL is listed in any sitemap
            sitemaps = idx_status.get("sitemap", [])
            has_sitemap = isinstance(sitemaps, list) and len(sitemaps) > 0
            if not has_sitemap:
                # Also handle case where sitemap might be a non-empty string
                if isinstance(sitemaps, str) and sitemaps.strip():
                    has_sitemap = True

            if not has_sitemap:
                continue

            total_with_sitemap += 1
            verdict = idx_status.get("verdict", "")
            if verdict == "PASS":
                indexed_with_sitemap += 1
            else:
                not_indexed_sitemap_urls.append({
                    "url": url,
                    "verdict": verdict,
                    "coverage_state": idx_status.get("coverageState", "Unknown"),
                    "sitemaps": ", ".join(sitemaps) if isinstance(sitemaps, list) else str(sitemaps),
                })

        if total_with_sitemap == 0:
            return self._error_result(44, "No URLs with sitemap data found in inspection results")

        index_rate = indexed_with_sitemap / total_with_sitemap * 100
        not_indexed_count = total_with_sitemap - indexed_with_sitemap

        if index_rate < 50:
            severity = Severity.HIGH
        elif index_rate < 75:
            severity = Severity.MEDIUM
        else:
            severity = Severity.INSIGHT

        display_df = pd.DataFrame(not_indexed_sitemap_urls).head(25) if not_indexed_sitemap_urls else None

        summary = (
            f"{indexed_with_sitemap:,} of {total_with_sitemap:,} sitemap-listed URLs "
            f"({index_rate:.1f}%) are indexed. {not_indexed_count:,} URLs are in your "
            f"sitemap but not indexed, indicating sitemap quality or content issues."
        )

        recommendations = []
        if index_rate < 75:
            recommendations.extend([
                "Audit your sitemap to remove URLs that should not be indexed (redirects, 404s, noindexed pages).",
                "Ensure all sitemap URLs return 200 status codes and contain indexable content.",
                "Keep sitemaps focused on canonical, high-quality URLs only.",
                "Investigate why Google is choosing not to index pages you've explicitly submitted.",
                "Update sitemap lastmod timestamps to reflect actual content changes.",
            ])
        else:
            recommendations.append(
                "Sitemap index rate is healthy. Continue keeping your sitemap clean and up to date."
            )

        return self.create_result(
            metric_id=44,
            severity=severity,
            summary=summary,
            computed_value=round(index_rate, 2),
            affected_count=not_indexed_count,
            data_table=display_df,
            recommendations=recommendations,
            details={
                "total_sitemap_urls": total_with_sitemap,
                "indexed_sitemap_urls": indexed_with_sitemap,
                "not_indexed_sitemap_urls": not_indexed_count,
                "index_rate_pct": round(index_rate, 2),
            },
        )
