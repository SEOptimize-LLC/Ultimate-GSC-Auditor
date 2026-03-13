"""Number, percentage, position, and display formatting utilities."""


def format_number(n: int | float) -> str:
    """Format a number with thousands separator."""
    if isinstance(n, float) and n == int(n):
        n = int(n)
    if isinstance(n, int):
        return f"{n:,}"
    return f"{n:,.2f}"


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format a decimal value as a percentage string."""
    return f"{value * 100:.{decimals}f}%"


def format_position(position: float) -> str:
    """Format a ranking position."""
    return f"{position:.1f}"


def format_delta(value: float, is_percentage: bool = False) -> str:
    """Format a change value with + or - prefix."""
    sign = "+" if value > 0 else ""
    if is_percentage:
        return f"{sign}{value * 100:.1f}%"
    return f"{sign}{format_number(value)}"


def format_ctr(ctr: float) -> str:
    """Format CTR as a percentage."""
    return format_percentage(ctr, decimals=2)


def severity_color(severity: str) -> str:
    """Return the display color for a severity level."""
    colors = {
        "critical": "#DC3545",
        "high": "#FD7E14",
        "medium": "#FFC107",
        "low": "#0D6EFD",
        "insight": "#6C757D",
    }
    return colors.get(severity.lower(), "#6C757D")


def severity_emoji(severity: str) -> str:
    """Return the emoji for a severity level."""
    emojis = {
        "critical": "\U0001f534",
        "high": "\U0001f7e0",
        "medium": "\U0001f7e1",
        "low": "\U0001f535",
        "insight": "\u26aa",
    }
    return emojis.get(severity.lower(), "\u26aa")
