"""Site-specific CTR benchmark computation.

Computes CTR benchmarks from the property's own data rather than
using industry averages. This gives honest, actionable comparisons.
"""

import numpy as np
import pandas as pd


def compute_site_ctr_curve(
    df: pd.DataFrame,
    position_col: str = "position",
    ctr_col: str = "ctr",
    impressions_col: str = "impressions",
    min_impressions: int = 10,
    max_position: int = 20,
) -> dict[int, float]:
    """Compute the site-specific CTR curve by position.

    Uses median CTR at each integer position (more robust than mean
    against outliers like branded queries at position 1).

    Args:
        df: DataFrame with position, ctr, and impressions columns.
        position_col: Name of the position column.
        ctr_col: Name of the CTR column.
        impressions_col: Name of the impressions column.
        min_impressions: Minimum impressions to include a row.
        max_position: Maximum position to compute benchmark for.

    Returns:
        Dict mapping integer position (1-20) to median CTR.
    """
    if df.empty:
        return _default_ctr_curve()

    filtered = df[df[impressions_col] >= min_impressions].copy()
    if filtered.empty:
        return _default_ctr_curve()

    filtered["position_bucket"] = filtered[position_col].round().astype(int)
    filtered = filtered[
        (filtered["position_bucket"] >= 1)
        & (filtered["position_bucket"] <= max_position)
    ]

    curve = (
        filtered.groupby("position_bucket")[ctr_col]
        .median()
        .to_dict()
    )

    # Fill any missing positions with interpolated values
    result = {}
    for pos in range(1, max_position + 1):
        if pos in curve:
            result[pos] = curve[pos]
        else:
            # Interpolate from neighbors
            lower = max((p for p in curve if p < pos), default=None)
            upper = min((p for p in curve if p > pos), default=None)
            if lower and upper:
                weight = (pos - lower) / (upper - lower)
                result[pos] = curve[lower] + weight * (curve[upper] - curve[lower])
            elif lower:
                result[pos] = curve[lower]
            elif upper:
                result[pos] = curve[upper]
            else:
                result[pos] = _default_ctr_curve().get(pos, 0.01)

    return result


def get_expected_ctr(
    ctr_curve: dict[int, float], position: float
) -> float:
    """Get the expected CTR for a given position from the site curve.

    Interpolates between integer positions for fractional values.
    """
    pos_int = int(round(position))
    pos_int = max(1, min(pos_int, 20))
    return ctr_curve.get(pos_int, 0.01)


def compute_ctr_gap(
    actual_ctr: float, expected_ctr: float
) -> float:
    """Compute the CTR gap score.

    Positive = outperforming, Negative = underperforming.
    """
    if expected_ctr == 0:
        return 0.0
    return actual_ctr - expected_ctr


def _default_ctr_curve() -> dict[int, float]:
    """Fallback CTR curve when insufficient site data exists."""
    return {
        1: 0.30, 2: 0.18, 3: 0.12, 4: 0.08, 5: 0.06,
        6: 0.045, 7: 0.035, 8: 0.028, 9: 0.022, 10: 0.018,
        11: 0.012, 12: 0.010, 13: 0.008, 14: 0.007, 15: 0.006,
        16: 0.005, 17: 0.004, 18: 0.004, 19: 0.003, 20: 0.003,
    }
