"""Data models for plotting widget configuration.

Provides frozen dataclasses for configuring plot traces, styles, and axes.
Similar pattern to models.py for consistency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class PlotTraceStyle:
    """Style configuration for a single plot trace."""

    color: str = "#1f77b4"  # Default matplotlib blue
    line_width: float = 1.0
    point_size: float = 5.0
    symbol: str = "o"  # 'o', 's', 't', 'd', '+', 'x', etc. (pyqtgraph symbols)
    line_style: str = "solid"  # 'solid', 'dashed', 'dotted', 'dash_dot', 'none'
    show_points: bool = True
    show_line: bool = False  # Default to scatter mode
    alpha: float = 1.0  # Opacity (0.0 to 1.0)


@dataclass(frozen=True)
class PlotAxisConfig:
    """Configuration for plot axes."""

    label: str = ""
    log_mode: bool = False
    auto_range: bool = True
    range_min: Optional[float] = None
    range_max: Optional[float] = None
    grid: bool = True


@dataclass(frozen=True)
class PlotConfig:
    """Overall plot configuration."""

    title: str = ""
    x_axis: PlotAxisConfig = PlotAxisConfig()
    y_axis: PlotAxisConfig = PlotAxisConfig()
    legend: bool = True
    antialias: bool = True
    background_color: str = "w"  # 'w' for white, 'k' for black
    foreground_color: str = "k"  # Text/axis color


@dataclass(frozen=True)
class PlotTrace:
    """A single data trace on the plot."""

    name: str
    x_data: Tuple[float, ...]  # Using tuple for immutability
    y_data: Tuple[float, ...]
    feature_ids: Tuple[str, ...]  # Feature IDs for selection sync
    layer_id: str
    style: PlotTraceStyle = PlotTraceStyle()
    visible: bool = True
