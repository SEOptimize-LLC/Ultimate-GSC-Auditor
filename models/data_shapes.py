"""Data shape definitions for GSC API queries.

Each shape defines a unique combination of dimensions and date range
that gets fetched once and shared across multiple metrics.
The 100 metrics require ~20 unique data shapes.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DataShape:
    """A unique GSC API query configuration."""
    name: str
    dimensions: tuple[str, ...]
    days: int
    search_type: str  # web, discover, news, image, video
    description: str


# --- Search Analytics Shapes ---
SHAPES: dict[str, DataShape] = {
    # 90-day shapes
    "SA_01": DataShape("query_90d", ("query",), 90, "web", "Query-level metrics (90d)"),
    "SA_02": DataShape("page_90d", ("page",), 90, "web", "Page-level metrics (90d)"),
    "SA_03": DataShape("query_page_90d", ("query", "page"), 90, "web", "Query-to-page mapping (90d)"),
    "SA_04": DataShape("query_date_90d", ("query", "date"), 90, "web", "Query daily trends (90d)"),
    "SA_05": DataShape("page_date_90d", ("page", "date"), 90, "web", "Page daily trends (90d)"),
    "SA_06": DataShape("query_device_90d", ("query", "device"), 90, "web", "Query by device (90d)"),
    "SA_07": DataShape("page_device_90d", ("page", "device"), 90, "web", "Page by device (90d)"),
    "SA_08": DataShape("query_country_90d", ("query", "country"), 90, "web", "Query by country (90d)"),
    "SA_09": DataShape("page_country_90d", ("page", "country"), 90, "web", "Page by country (90d)"),
    "SA_10": DataShape("search_appearance_90d", ("searchAppearance",), 90, "web", "SERP feature metrics (90d)"),
    # SA_11 removed — GSC API does not allow searchAppearance
    # combined with other dimensions.

    # 365-day shapes
    "SA_12": DataShape("page_date_365d", ("page", "date"), 365, "web", "Page daily trends (365d)"),
    "SA_13": DataShape("query_date_365d", ("query", "date"), 365, "web", "Query daily trends (365d)"),
    "SA_14": DataShape("query_365d", ("query",), 365, "web", "Query-level metrics (365d)"),
    "SA_15": DataShape("page_365d", ("page",), 365, "web", "Page-level metrics (365d)"),
    "SA_16": DataShape("query_page_365d", ("query", "page"), 365, "web", "Query-to-page mapping (365d)"),

    # 30-day shapes (for current month in MoM calculations)
    "SA_17": DataShape("query_date_30d", ("query", "date"), 30, "web", "Query daily trends (30d)"),
    "SA_18": DataShape("page_date_30d", ("page", "date"), 30, "web", "Page daily trends (30d)"),

    # Multi-dimension shapes
    "SA_19": DataShape("query_page_date_90d", ("query", "page", "date"), 90, "web", "Query-page daily trends (90d)"),

    # Search type specific shapes (for image, video, discover, news impression shares)
    "SA_20": DataShape("page_discover_90d", ("page",), 90, "discover", "Discover impressions by page (90d)"),
    "SA_21": DataShape("page_news_90d", ("page",), 90, "news", "News impressions by page (90d)"),
    "SA_22": DataShape("page_image_90d", ("page",), 90, "image", "Image impressions by page (90d)"),
    "SA_23": DataShape("page_video_90d", ("page",), 90, "video", "Video impressions by page (90d)"),
}

# --- Metric-to-Shape Dependencies ---
# Maps each metric ID (1-100) to the shape keys it requires
METRIC_SHAPES: dict[int, list[str]] = {
    # Query Performance (1-12)
    1: ["SA_03"],  # Query Count per URL — needs query-page mapping
    2: ["SA_03"],  # Click-Generating Query Rate — needs query-page mapping
    3: ["SA_01"],  # Zero-Click Query Count — query level
    4: ["SA_01"],  # Top-3 Query Share
    5: ["SA_01"],  # Top-10 Query Share
    6: ["SA_01"],  # Striking Distance Query Count (pos 11-20)
    7: ["SA_01"],  # Position 21-50 Query Count
    8: ["SA_01"],  # Branded vs Non-Branded Query Ratio (needs AI)
    9: ["SA_03"],  # Query Impression Share per URL
    10: ["SA_04", "SA_17"],  # Query Retention Rate MoM
    11: ["SA_04", "SA_13"],  # Query Retention Rate YoY
    12: ["SA_04", "SA_17"],  # New Query Emergence Rate

    # Click & CTR (13-21)
    13: ["SA_02"],  # Click Share per URL
    14: ["SA_01"],  # CTR Gap Score (needs site-specific benchmarks)
    15: ["SA_02"],  # High-Impression Zero-Click URL Count
    16: ["SA_01"],  # Click Efficiency Rate
    17: ["SA_05", "SA_18"],  # MoM Click Delta
    18: ["SA_05", "SA_12"],  # YoY Click Delta
    19: ["SA_01"],  # CTR Decay Rate
    20: ["SA_12"],  # Seasonal Click Index
    21: ["SA_02"],  # Click Concentration Rate

    # Impression & Visibility (22-27)
    22: ["SA_05", "SA_18"],  # Impression Growth Rate MoM
    23: ["SA_05", "SA_12"],  # Impression Growth Rate YoY
    24: ["SA_10"],  # SERP Feature Impression Share
    25: ["SA_10"],  # Featured Snippet Impression Rate
    26: ["SA_03"],  # Share of Voice by Topic Cluster (needs AI)
    27: ["SA_03"],  # Query Impression Depth

    # Position & Ranking (28-34)
    28: ["SA_05", "SA_18"],  # Average Position Drift MoM
    29: ["SA_05", "SA_12"],  # Average Position Drift YoY
    30: ["SA_19"],  # Rank Volatility Score
    31: ["SA_19"],  # Top-3 Query Gain/Loss Count MoM
    32: ["SA_19"],  # Position Improvement Rate
    33: ["SA_19"],  # Position Degradation Rate
    34: ["SA_03", "SA_16"],  # Query Cannibalization Score

    # Crawl & Index Health (35-44) — URL Inspection API
    35: [],  # URL Crawl Rate (30d) — URL_INSPECTION
    36: [],  # URL Crawl Rate (90d) — URL_INSPECTION
    37: [],  # Crawl Frequency per URL — URL_INSPECTION
    38: [],  # Days Since Last Crawl — URL_INSPECTION
    39: [],  # Discovered-but-Not-Crawled Rate — URL_INSPECTION
    40: [],  # Crawled-but-Not-Indexed Rate — URL_INSPECTION
    41: [],  # Indexed URL Coverage Rate — URL_INSPECTION
    42: [],  # Coverage Error Rate — URL_INSPECTION
    43: ["SA_02"],  # Crawl Budget Efficiency Ratio — URL_INSPECTION + page data
    44: [],  # Sitemap-Sourced Index Rate — URL_INSPECTION + SITEMAPS

    # Content Health & Decay (45-48)
    45: ["SA_05", "SA_12"],  # Content Decay Index
    46: ["SA_03"],  # Thin Content Query Rate
    47: ["SA_03"],  # Content Efficiency Ratio
    48: ["SA_05", "SA_18"],  # MoM New URL Click Share

    # Device & Segment (49-50)
    49: ["SA_06", "SA_07"],  # Mobile vs Desktop CTR Gap
    50: ["SA_07"],  # Mobile Impression Share

    # Query Intent & Topical (51-60)
    51: ["SA_01"],  # Informational Query Share (needs AI)
    52: ["SA_01"],  # Transactional Query Share (needs AI)
    53: ["SA_01"],  # Navigational Query Share (needs AI)
    54: ["SA_01"],  # Long-Tail Query Rate (4+ words)
    55: ["SA_01"],  # Head Term Query Rate (1-2 words)
    56: ["SA_01"],  # Question-Format Query Share
    57: ["SA_01"],  # Query Diversity Score
    58: ["SA_01"],  # Single-Impression Query Rate
    59: ["SA_03"],  # Query Overlap Rate Across URLs
    60: ["SA_13"],  # Seasonal Query Concentration

    # Click Behavior (61-68)
    61: ["SA_01"],  # High-Position Zero-Click Rate
    62: ["SA_01"],  # Single-Click Query Rate
    63: ["SA_05", "SA_18"],  # Click-to-Impression Acceleration Rate
    64: ["SA_03"],  # Top Query Click Concentration
    65: ["SA_01"],  # Click Depth Distribution
    66: ["SA_02"],  # Underperforming High-Impression URL Rate
    67: ["SA_12"],  # Click Recovery Rate (Post-Drop)
    68: ["SA_07"],  # Multi-Device Click Share

    # Impression Quality (69-77)
    69: ["SA_01"],  # Page 1 Impression Share
    70: ["SA_01"],  # Page 2 Impression Share
    71: ["SA_01"],  # Deep-Page Impression Rate (pos 51+)
    72: ["SA_05", "SA_18"],  # Impression-to-Click Funnel Loss Rate
    73: ["SA_04", "SA_17"],  # New vs Returning Query Impression Split
    74: ["SA_10"],  # Rich Result Impression Rate
    75: ["SA_23"],  # Video Result Impression Share
    76: ["SA_22"],  # Image Result Impression Share
    77: ["SA_20", "SA_21"],  # News/Discover Impression Share

    # Ranking Velocity & Momentum (78-84)
    78: ["SA_19"],  # Ranking Velocity Score
    79: ["SA_04", "SA_17"],  # Query Acceleration Rate
    80: ["SA_19"],  # Position Stabilization Rate
    81: ["SA_19"],  # Fast-Rising Query Count
    82: ["SA_19"],  # Fast-Falling Query Count
    83: ["SA_12"],  # Rank Recovery Speed
    84: ["SA_01"],  # Position 11 Proximity Rate

    # Indexation & Coverage Health (85-94) — URL Inspection API
    85: [],  # Soft 404 Rate — URL_INSPECTION
    86: [],  # Redirect Chain Indexed URL Rate — URL_INSPECTION
    87: [],  # Alternate Page Suppression Rate — URL_INSPECTION
    88: [],  # Duplicate URL Index Pollution Rate — URL_INSPECTION
    89: [],  # Excluded URL Rate — URL_INSPECTION
    90: [],  # Server Error Crawl Rate — URL_INSPECTION
    91: [],  # Not-Found Crawl Rate — URL_INSPECTION
    92: [],  # Robots.txt Block Rate — URL_INSPECTION
    93: [],  # Noindex Tag Rate — URL_INSPECTION
    94: [],  # Crawl Freshness Index — URL_INSPECTION

    # Content Portfolio & Library Health (95-100)
    95: ["SA_02", "SA_15"],  # Active URL Rate
    96: ["SA_02", "SA_15"],  # Dead Weight URL Rate
    97: ["SA_03", "SA_16"],  # Content Cannibalization Cluster Count (needs AI)
    98: ["SA_05", "SA_18"],  # New Content Traction Rate
    99: ["SA_03"],  # Content Consolidation Opportunity Rate
    100: ["SA_02"],  # Top-10% URL Traffic Concentration
}

# Metrics that require URL Inspection API data
METRICS_NEEDING_URL_INSPECTION = set(range(35, 45)) | set(range(85, 95))

# Metrics that require Sitemaps API data
METRICS_NEEDING_SITEMAPS = {44}

# Metrics that require AI pre-processing
METRICS_NEEDING_AI = {8, 26, 51, 52, 53, 97}

# Metric categories
METRIC_CATEGORIES: dict[str, tuple[int, int]] = {
    "Query Performance": (1, 12),
    "Click & CTR": (13, 21),
    "Impression & Visibility": (22, 27),
    "Position & Ranking": (28, 34),
    "Crawl & Index Health": (35, 44),
    "Content Health & Decay": (45, 48),
    "Device & Segment": (49, 50),
    "Query Intent & Topical": (51, 60),
    "Click Behavior": (61, 68),
    "Impression Quality": (69, 77),
    "Ranking Velocity & Momentum": (78, 84),
    "Indexation & Coverage Health": (85, 94),
    "Content Portfolio & Library Health": (95, 100),
}

# Metric names
METRIC_NAMES: dict[int, str] = {
    1: "Query Count per URL",
    2: "Click-Generating Query Rate",
    3: "Zero-Click Query Count",
    4: "Top-3 Query Share",
    5: "Top-10 Query Share",
    6: "Striking Distance Query Count",
    7: "Position 21-50 Query Count",
    8: "Branded vs Non-Branded Query Ratio",
    9: "Query Impression Share per URL",
    10: "Query Retention Rate (MoM)",
    11: "Query Retention Rate (YoY)",
    12: "New Query Emergence Rate",
    13: "Click Share per URL",
    14: "CTR Gap Score",
    15: "High-Impression Zero-Click URL Count",
    16: "Click Efficiency Rate",
    17: "MoM Click Delta",
    18: "YoY Click Delta",
    19: "CTR Decay Rate",
    20: "Seasonal Click Index",
    21: "Click Concentration Rate",
    22: "Impression Growth Rate (MoM)",
    23: "Impression Growth Rate (YoY)",
    24: "SERP Feature Impression Share",
    25: "Featured Snippet Impression Rate",
    26: "Share of Voice by Topic Cluster",
    27: "Query Impression Depth",
    28: "Average Position Drift (MoM)",
    29: "Average Position Drift (YoY)",
    30: "Rank Volatility Score",
    31: "Top-3 Query Gain/Loss Count (MoM)",
    32: "Position Improvement Rate",
    33: "Position Degradation Rate",
    34: "Query Cannibalization Score",
    35: "URL Crawl Rate (Last 30 Days)",
    36: "URL Crawl Rate (Last 90 Days)",
    37: "Crawl Frequency per URL",
    38: "Days Since Last Crawl",
    39: "Discovered-but-Not-Crawled Rate",
    40: "Crawled-but-Not-Indexed Rate",
    41: "Indexed URL Coverage Rate",
    42: "Coverage Error Rate",
    43: "Crawl Budget Efficiency Ratio",
    44: "Sitemap-Sourced Index Rate",
    45: "Content Decay Index",
    46: "Thin Content Query Rate",
    47: "Content Efficiency Ratio",
    48: "MoM New URL Click Share",
    49: "Mobile vs Desktop CTR Gap",
    50: "Mobile Impression Share",
    51: "Informational Query Share",
    52: "Transactional Query Share",
    53: "Navigational Query Share",
    54: "Long-Tail Query Rate",
    55: "Head Term Query Rate",
    56: "Question-Format Query Share",
    57: "Query Diversity Score",
    58: "Single-Impression Query Rate",
    59: "Query Overlap Rate Across URLs",
    60: "Seasonal Query Concentration",
    61: "High-Position Zero-Click Rate",
    62: "Single-Click Query Rate",
    63: "Click-to-Impression Acceleration Rate",
    64: "Top Query Click Concentration",
    65: "Click Depth Distribution",
    66: "Underperforming High-Impression URL Rate",
    67: "Click Recovery Rate (Post-Drop)",
    68: "Multi-Device Click Share",
    69: "Page 1 Impression Share",
    70: "Page 2 Impression Share",
    71: "Deep-Page Impression Rate",
    72: "Impression-to-Click Funnel Loss Rate",
    73: "New vs Returning Query Impression Split",
    74: "Rich Result Impression Rate",
    75: "Video Result Impression Share",
    76: "Image Result Impression Share",
    77: "News/Discover Impression Share",
    78: "Ranking Velocity Score",
    79: "Query Acceleration Rate",
    80: "Position Stabilization Rate",
    81: "Fast-Rising Query Count",
    82: "Fast-Falling Query Count",
    83: "Rank Recovery Speed",
    84: "Position 11 Proximity Rate",
    85: "Soft 404 Rate",
    86: "Redirect Chain Indexed URL Rate",
    87: "Alternate Page Suppression Rate",
    88: "Duplicate URL Index Pollution Rate",
    89: "Excluded URL Rate",
    90: "Server Error Crawl Rate",
    91: "Not-Found Crawl Rate",
    92: "Robots.txt Block Rate",
    93: "Noindex Tag Rate",
    94: "Crawl Freshness Index",
    95: "Active URL Rate",
    96: "Dead Weight URL Rate",
    97: "Content Cannibalization Cluster Count",
    98: "New Content Traction Rate",
    99: "Content Consolidation Opportunity Rate",
    100: "Top-10% URL Traffic Concentration",
}


def get_required_shapes(metric_ids: list[int]) -> set[str]:
    """Determine which data shapes are required for the given metrics."""
    shapes: set[str] = set()
    for mid in metric_ids:
        shapes.update(METRIC_SHAPES.get(mid, []))
    return shapes


def needs_url_inspection(metric_ids: list[int]) -> bool:
    """Check if any selected metrics require URL Inspection API."""
    return bool(set(metric_ids) & METRICS_NEEDING_URL_INSPECTION)


def needs_sitemaps(metric_ids: list[int]) -> bool:
    """Check if any selected metrics require Sitemaps API."""
    return bool(set(metric_ids) & METRICS_NEEDING_SITEMAPS)


def needs_ai_preprocessing(metric_ids: list[int]) -> bool:
    """Check if any selected metrics require AI pre-processing."""
    return bool(set(metric_ids) & METRICS_NEEDING_AI)


def get_category_for_metric(metric_id: int) -> str:
    """Get the category name for a given metric ID."""
    for category, (start, end) in METRIC_CATEGORIES.items():
        if start <= metric_id <= end:
            return category
    return "Unknown"


def get_metrics_in_category(category: str) -> list[int]:
    """Get all metric IDs in a given category."""
    if category in METRIC_CATEGORIES:
        start, end = METRIC_CATEGORIES[category]
        return list(range(start, end + 1))
    return []
