"""URL filter configuration and rule definitions."""

from dataclasses import dataclass, field
import re
from typing import Optional


@dataclass
class FilterRule:
    """A single URL filter rule."""
    pattern: str
    rule_type: str  # "exclude" or "include"
    category: str  # e.g., "legal", "non-seo", "pagination"
    description: str
    enabled: bool = True

    def matches(self, url: str) -> bool:
        """Check if a URL matches this rule's pattern."""
        url_lower = url.lower()
        pattern_lower = self.pattern.lower()

        if pattern_lower.endswith("*"):
            return pattern_lower[:-1] in url_lower
        if pattern_lower.startswith("*"):
            return url_lower.endswith(pattern_lower[1:])
        return pattern_lower in url_lower


# Default exclusion rules
DEFAULT_EXCLUDE_RULES: list[FilterRule] = [
    # Legal pages
    FilterRule("/privacy-policy", "exclude", "legal", "Privacy policy pages"),
    FilterRule("/privacy", "exclude", "legal", "Privacy pages"),
    FilterRule("/terms-of-service", "exclude", "legal", "Terms of service pages"),
    FilterRule("/terms-and-conditions", "exclude", "legal", "Terms and conditions pages"),
    FilterRule("/terms", "exclude", "legal", "Terms pages"),
    FilterRule("/cookie-policy", "exclude", "legal", "Cookie policy pages"),
    FilterRule("/disclaimer", "exclude", "legal", "Disclaimer pages"),
    FilterRule("/shipping-policy", "exclude", "legal", "Shipping policy pages"),
    FilterRule("/return-policy", "exclude", "legal", "Return/refund policy pages"),
    FilterRule("/refund-policy", "exclude", "legal", "Refund policy pages"),
    FilterRule("/accessibility-statement", "exclude", "legal", "Accessibility statement"),

    # Non-SEO pages
    FilterRule("/about-us", "exclude", "non-seo", "About us pages"),
    FilterRule("/about", "exclude", "non-seo", "About pages"),
    FilterRule("/contact-us", "exclude", "non-seo", "Contact us pages"),
    FilterRule("/contact", "exclude", "non-seo", "Contact pages"),
    FilterRule("/careers", "exclude", "non-seo", "Careers pages"),
    FilterRule("/jobs", "exclude", "non-seo", "Jobs pages"),
    FilterRule("/team", "exclude", "non-seo", "Team pages"),
    FilterRule("/our-team", "exclude", "non-seo", "Our team pages"),

    # Pagination
    FilterRule("?page=", "exclude", "pagination", "Paginated pages (query param)"),
    FilterRule("/page/", "exclude", "pagination", "Paginated pages (path)"),

    # Tracking parameters
    FilterRule("?utm_", "exclude", "tracking", "UTM tracking parameters"),
    FilterRule("?fbclid", "exclude", "tracking", "Facebook click ID"),
    FilterRule("?gclid", "exclude", "tracking", "Google click ID"),
    FilterRule("?msclkid", "exclude", "tracking", "Microsoft click ID"),

    # CMS artifacts
    FilterRule("/wp-admin/", "exclude", "cms", "WordPress admin pages"),
    FilterRule("/wp-login", "exclude", "cms", "WordPress login pages"),
    FilterRule("/wp-json/", "exclude", "cms", "WordPress API endpoints"),
    FilterRule("/feed/", "exclude", "cms", "RSS feed pages"),
    FilterRule("/feed", "exclude", "cms", "RSS feed"),
    FilterRule(".xml", "exclude", "cms", "XML files (sitemaps, feeds)"),

    # User account pages
    FilterRule("/cart", "exclude", "account", "Shopping cart"),
    FilterRule("/checkout", "exclude", "account", "Checkout pages"),
    FilterRule("/my-account", "exclude", "account", "User account pages"),
    FilterRule("/account", "exclude", "account", "Account pages"),
    FilterRule("/login", "exclude", "account", "Login pages"),
    FilterRule("/register", "exclude", "account", "Registration pages"),
    FilterRule("/signup", "exclude", "account", "Sign up pages"),

    # Taxonomy pages
    FilterRule("/tag/", "exclude", "taxonomy", "Tag archive pages"),
    FilterRule("/author/", "exclude", "taxonomy", "Author archive pages"),
    FilterRule("/category/", "exclude", "taxonomy", "Category archive pages"),

    # AMP pages
    FilterRule("/amp/", "exclude", "amp", "AMP versions (typically duplicates)"),
    FilterRule("?amp", "exclude", "amp", "AMP query parameter"),
]

# Default include rules (these override excludes)
DEFAULT_INCLUDE_RULES: list[FilterRule] = [
    FilterRule("/blog/*", "include", "content", "Blog content pages"),
    FilterRule("/articles/*", "include", "content", "Article pages"),
    FilterRule("/resources/*", "include", "content", "Resource pages"),
    FilterRule("/services/*", "include", "content", "Service pages"),
    FilterRule("/products/*", "include", "content", "Product pages"),
]

# Categories for UI organization
FILTER_CATEGORIES = {
    "legal": "Legal & Policy Pages",
    "non-seo": "Non-SEO Pages",
    "pagination": "Pagination",
    "tracking": "Tracking Parameters",
    "cms": "CMS Artifacts",
    "account": "User Account Pages",
    "taxonomy": "Taxonomy Archives",
    "amp": "AMP Pages",
    "content": "Content Pages (Include)",
}


@dataclass
class URLFilterConfig:
    """Complete URL filter configuration."""
    exclude_rules: list[FilterRule] = field(default_factory=lambda: list(DEFAULT_EXCLUDE_RULES))
    include_rules: list[FilterRule] = field(default_factory=lambda: list(DEFAULT_INCLUDE_RULES))
    custom_exclude_patterns: list[str] = field(default_factory=list)
    custom_include_patterns: list[str] = field(default_factory=list)

    def should_include(self, url: str) -> bool:
        """Determine if a URL should be included in the analysis.

        Logic:
        1. Check custom include patterns first (always include if matched)
        2. Check default include rules
        3. Check custom exclude patterns
        4. Check default exclude rules
        5. Homepage is always included
        6. Default: include
        """
        from utils.url_utils import is_homepage

        # Homepage is always included
        if is_homepage(url):
            return True

        # Custom include patterns override everything
        for pattern in self.custom_include_patterns:
            if pattern.lower() in url.lower():
                return True

        # Check default include rules
        for rule in self.include_rules:
            if rule.enabled and rule.matches(url):
                return True

        # Check custom exclude patterns
        for pattern in self.custom_exclude_patterns:
            if pattern.lower() in url.lower():
                return False

        # Check default exclude rules
        for rule in self.exclude_rules:
            if rule.enabled and rule.matches(url):
                return False

        # Default: include
        return True

    def filter_urls(self, urls: list[str]) -> tuple[list[str], list[str]]:
        """Filter a list of URLs into included and excluded lists.

        Returns:
            (included_urls, excluded_urls)
        """
        included = []
        excluded = []
        for url in urls:
            if self.should_include(url):
                included.append(url)
            else:
                excluded.append(url)
        return included, excluded

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return {
            "exclude_rules": [
                {"pattern": r.pattern, "category": r.category, "enabled": r.enabled}
                for r in self.exclude_rules
            ],
            "include_rules": [
                {"pattern": r.pattern, "category": r.category, "enabled": r.enabled}
                for r in self.include_rules
            ],
            "custom_exclude_patterns": self.custom_exclude_patterns,
            "custom_include_patterns": self.custom_include_patterns,
        }
