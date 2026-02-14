from __future__ import annotations

import numpy as np


def clamp(value: float, vmin: float = 0.0, vmax: float = 1.0) -> float:
    """Clamp numeric values to [vmin, vmax]."""
    lo = float(vmin)
    hi = float(vmax)
    if lo > hi:
        lo, hi = hi, lo

    try:
        v = float(value)
    except (TypeError, ValueError):
        return lo

    if not np.isfinite(v):
        return lo

    return float(np.clip(v, lo, hi))
