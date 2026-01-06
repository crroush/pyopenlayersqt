from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal, Optional

Color = tuple[int, int, int, int]  # RGBA 0-255


@dataclass(frozen=True)
class PointStyle:
    radius: int = 5
    fill: Color = (0, 120, 255, 170)
    stroke: Color = (0, 0, 0, 80)
    stroke_width: int = 1
    selected_radius: int = 7
    selected_fill: Color = (255, 50, 50, 220)
    selected_stroke: Color = (0, 0, 0, 120)
    selected_stroke_width: int = 1


@dataclass(frozen=True)
class PolygonStyle:
    fill: Color = (0, 120, 255, 80)
    stroke: Color = (0, 120, 255, 200)
    stroke_width: int = 2
    selected_fill: Color = (255, 50, 50, 90)
    selected_stroke: Color = (255, 50, 50, 230)
    selected_stroke_width: int = 2


@dataclass(frozen=True)
class RasterStyle:
    opacity: float = 0.55


@dataclass(frozen=True)
class WMSOptions:
    name: str
    url: str
    layers: str
    opacity: float = 0.6
    visible: bool = True
    params: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class SelectEvent:
    type: Literal["select"] = "select"
    layer: str = ""
    ids: list[Any] = None  # feature ids
    features: list[dict[str, Any]] = None  # arbitrary props incl lon/lat/z
