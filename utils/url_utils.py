"""URL parsing, normalization, and utility functions."""

from urllib.parse import urlparse, urlunparse, parse_qs, urlencode


def normalize_url(url: str) -> str:
    """Normalize a URL by removing trailing slashes and fragments."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        parsed.params,
        parsed.query,
        "",  # remove fragment
    ))
    return normalized


def extract_path(url: str) -> str:
    """Extract the path component from a URL."""
    return urlparse(url).path or "/"


def extract_domain(url: str) -> str:
    """Extract the domain (netloc) from a URL."""
    return urlparse(url).netloc


def extract_directory(url: str) -> str:
    """Extract the first-level directory from a URL path.

    Example: 'https://example.com/blog/my-post' -> '/blog/'
    """
    path = extract_path(url)
    parts = path.strip("/").split("/")
    if parts and parts[0]:
        return f"/{parts[0]}/"
    return "/"


def has_parameters(url: str) -> bool:
    """Check if a URL has query parameters."""
    return bool(urlparse(url).query)


def get_parameters(url: str) -> dict[str, list[str]]:
    """Extract query parameters from a URL."""
    return parse_qs(urlparse(url).query)


def strip_parameters(url: str) -> str:
    """Remove all query parameters from a URL."""
    parsed = urlparse(url)
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        "",
        "",
    ))


def is_homepage(url: str) -> bool:
    """Check if a URL is the homepage."""
    path = extract_path(url).strip("/")
    return path == "" or path == "/"
