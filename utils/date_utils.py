"""Date range and period calculation utilities."""

from datetime import date, datetime, timedelta


GSC_DATA_DELAY_DAYS = 3  # GSC data typically has a 2-3 day lag


def get_date_range(days: int) -> tuple[str, str]:
    """Calculate start/end dates accounting for GSC data lag.

    Returns (start_date, end_date) as ISO format strings.
    """
    end = date.today() - timedelta(days=GSC_DATA_DELAY_DAYS)
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def get_comparison_ranges(
    days: int, comparison: str = "mom"
) -> tuple[tuple[str, str], tuple[str, str]]:
    """Calculate current and comparison date ranges.

    Args:
        days: Number of days for each period.
        comparison: 'mom' for month-over-month, 'yoy' for year-over-year.

    Returns:
        ((current_start, current_end), (previous_start, previous_end))
    """
    current_end = date.today() - timedelta(days=GSC_DATA_DELAY_DAYS)
    current_start = current_end - timedelta(days=days)

    if comparison == "yoy":
        previous_end = current_end.replace(year=current_end.year - 1)
        previous_start = current_start.replace(year=current_start.year - 1)
    else:  # mom
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=days)

    return (
        (current_start.isoformat(), current_end.isoformat()),
        (previous_start.isoformat(), previous_end.isoformat()),
    )


def parse_date(date_str: str) -> date:
    """Parse an ISO format date string."""
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def days_between(date_str1: str, date_str2: str) -> int:
    """Calculate the number of days between two ISO date strings."""
    d1 = parse_date(date_str1)
    d2 = parse_date(date_str2)
    return abs((d2 - d1).days)


def split_into_periods(
    start_date: str, end_date: str, period_days: int
) -> list[tuple[str, str]]:
    """Split a date range into equal periods.

    Useful for MoM trending over a longer range.
    """
    periods = []
    start = parse_date(start_date)
    end = parse_date(end_date)

    while start < end:
        period_end = min(start + timedelta(days=period_days - 1), end)
        periods.append((start.isoformat(), period_end.isoformat()))
        start = period_end + timedelta(days=1)

    return periods
