from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

# "#RRGGBB", "rgba(...)", or tuples
Color = Union[str, Tuple[int, int, int], Tuple[int, int, int, int]]
LatLon = Tuple[float, float]  # (lat, lon) - Public API uses latitude first


def _qcolor_to_rgba(color: Any) -> tuple[int, int, int, int]:
    """Convert a QColor object to an RGBA tuple.
    
    Args:
        color: QColor object from PySide6.QtGui
        
    Returns:
        Tuple of (r, g, b, a) with values 0-255.
    """
    # Import here to avoid circular dependency and allow models.py to work without Qt
    try:
        from PySide6.QtGui import QColor
        if isinstance(color, QColor):
            return (color.red(), color.green(), color.blue(), color.alpha())
    except ImportError:
        pass
    raise TypeError(f"Expected QColor object, got {type(color)}")


def _color_name_to_rgba(color_name: str) -> tuple[int, int, int, int]:
    """Convert a color name (e.g., 'Green', 'Red') to RGBA tuple using QColor.
    
    Args:
        color_name: Color name (e.g., 'Green', 'Red', 'blue')
        
    Returns:
        Tuple of (r, g, b, a) with values 0-255.
    """
    try:
        from PySide6.QtGui import QColor
        qcolor = QColor(color_name)
        if qcolor.isValid():
            return (qcolor.red(), qcolor.green(), qcolor.blue(), qcolor.alpha())
    except ImportError:
        pass
    raise ValueError(f"Invalid color name: {color_name}")


def _normalize_color_to_rgba(
    color: Union[tuple[int, int, int, int], str, Any]
) -> tuple[int, int, int, int]:
    """Normalize a color to RGBA tuple format.
    
    Accepts:
    - RGBA tuple: (r, g, b, a) with values 0-255
    - QColor object from PySide6.QtGui
    - Color name string (e.g., 'Green', 'Red')
    
    Args:
        color: RGBA tuple, QColor object, or color name string
        
    Returns:
        Tuple of (r, g, b, a) with values 0-255.
    """
    # Already an RGBA tuple
    if isinstance(color, tuple) and len(color) == 4:
        return color
    
    # Try to convert from QColor
    try:
        from PySide6.QtGui import QColor
        if isinstance(color, QColor):
            return _qcolor_to_rgba(color)
    except ImportError:
        pass
    
    # Try as a color name string
    if isinstance(color, str):
        return _color_name_to_rgba(color)
    
    raise TypeError(
        f"Color must be an RGBA tuple (r, g, b, a), a QColor object, "
        f"or a color name string, got {type(color)}"
    )


def _color_to_css(c: Union[Color, Any], alpha: Optional[float] = None) -> str:
    """
    Convert color into a CSS color string.
    - Accepts "#RRGGBB", "rgba(...)", "rgb(...)", (r,g,b) / (r,g,b,a) tuples, 
      QColor objects, or color name strings (e.g., 'Green', 'Red').
    - If alpha is provided, it overrides tuple alpha and converts rgb tuple to rgba.
    """
    # First, try to convert QColor or color names to RGBA tuple
    try:
        from PySide6.QtGui import QColor
        # If it's a QColor object, convert it to RGBA tuple
        if isinstance(c, QColor):
            c = (c.red(), c.green(), c.blue(), c.alpha())
    except ImportError:
        pass
    
    # Handle string inputs
    if isinstance(c, str):
        # Try to interpret as color name using QColor
        try:
            from PySide6.QtGui import QColor
            qcolor = QColor(c)
            if qcolor.isValid() and not c.startswith("#") and not c.startswith("rgb"):
                # It's a valid color name like 'Green', convert to tuple
                c = (qcolor.red(), qcolor.green(), qcolor.blue(), qcolor.alpha())
            else:
                # It's a hex color or CSS string, handle below
                pass
        except ImportError:
            pass
        
        # If still a string, handle hex and CSS strings
        if isinstance(c, str):
            # If caller passes "rgba(...)" already, honor it.
            if alpha is None:
                return c
            # If it's a hex like "#RRGGBB", wrap into rgba by parsing.
            if c.startswith("#") and len(c) == 7:
                r = int(c[1:3], 16)
                g = int(c[3:5], 16)
                b = int(c[5:7], 16)
                return f"rgba({r},{g},{b},{alpha})"
            # Otherwise just return original string (best effort)
            return c

    # Handle tuples
    if len(c) == 3:
        r, g, b = c
        a = alpha if alpha is not None else 1.0
        return f"rgba({r},{g},{b},{a})"

    r, g, b, a0 = c
    a = alpha if alpha is not None else (a0 / 255.0 if a0 > 1 else float(a0))
    return f"rgba({r},{g},{b},{a})"


@dataclass(frozen=True)
class PointStyle:
    """
    Point style (rendered as a circle marker).

    radius: pixels
    fill_color / fill_opacity: marker fill
    stroke_color / stroke_width / stroke_opacity: marker outline
    """
    radius: float = 5.0
    fill_color: Color = "#ff3333"
    fill_opacity: float = 0.85
    stroke_color: Color = "#000000"
    stroke_width: float = 1.0
    stroke_opacity: float = 0.9

    def to_js(self) -> Dict[str, Any]:
        return {
            "radius": float(self.radius),
            "fill": _color_to_css(self.fill_color, self.fill_opacity),
            "stroke": _color_to_css(self.stroke_color, self.stroke_opacity),
            "stroke_width": float(self.stroke_width),
        }


@dataclass(frozen=True)
class CircleStyle:
    """
    Circle feature style (geodesic-ish circle drawn on map; rendered as polygon in OL)
    - radius_m: meters
    - outline + optional fill
    """
    stroke_color: Color = "#00aaff"
    stroke_width: float = 2.0
    stroke_opacity: float = 0.95
    fill_color: Color = "#00aaff"
    fill_opacity: float = 0.15
    fill: bool = True

    def to_js(self) -> Dict[str, Any]:
        return {
            "stroke": _color_to_css(self.stroke_color, self.stroke_opacity),
            "stroke_width": float(self.stroke_width),
            "fill": (
                _color_to_css(self.fill_color, self.fill_opacity)
                if self.fill else "rgba(0,0,0,0)"
            ),
        }


@dataclass(frozen=True)
class PolygonStyle:
    """
    Polygon (and arbitrary geometry) style.
    """
    stroke_color: Color = "#00aaff"
    stroke_width: float = 2.0
    stroke_opacity: float = 0.95
    fill_color: Color = "#00aaff"
    fill_opacity: float = 0.15
    fill: bool = True

    def to_js(self) -> Dict[str, Any]:
        return {
            "stroke": _color_to_css(self.stroke_color, self.stroke_opacity),
            "stroke_width": float(self.stroke_width),
            "fill": (
                _color_to_css(self.fill_color, self.fill_opacity)
                if self.fill else "rgba(0,0,0,0)"
            ),
        }


@dataclass(frozen=True)
class EllipseStyle:
    """
    Ellipse style. Ellipse is represented in JS as a polygon approximating an ellipse.

    stroke + optional fill.
    """
    stroke_color: Color = "#ffcc00"
    stroke_width: float = 2.0
    stroke_opacity: float = 0.95
    fill_color: Color = "#ffcc00"
    fill_opacity: float = 0.12
    fill: bool = True

    def to_js(self) -> Dict[str, Any]:
        return {
            "stroke": _color_to_css(self.stroke_color, self.stroke_opacity),
            "stroke_width": float(self.stroke_width),
            "fill": (
                _color_to_css(self.fill_color, self.fill_opacity)
                if self.fill else "rgba(0,0,0,0)"
            ),
        }


@dataclass(frozen=True)
class RasterStyle:
    """
    Raster overlay style (image overlay).
    opacity: 0..1
    """
    opacity: float = 0.6

    def to_js(self) -> Dict[str, Any]:
        return {"opacity": float(self.opacity)}


@dataclass(frozen=True)
class WMSOptions:
    """
    WMS layer options.

    url: WMS endpoint base URL
    params: dict passed to ol/source/TileWMS (e.g. {"LAYERS":"foo","TILED":True})
    opacity: 0..1
    """
    url: str
    params: Dict[str, Any]
    opacity: float = 1.0

    def to_js(self) -> Dict[str, Any]:
        return {"url": self.url, "params": dict(self.params), "opacity": float(self.opacity)}


@dataclass(frozen=True)
class HeatmapOptions:
    """
    "heatmap" from scattered points (lon/lat, z).
    We render as a raster PNG on Python side, then use ImageStatic overlay in OL.

    opacity: 0..1
    colormap: matplotlib colormap name (e.g. "viridis")
    vmin/vmax: optional fixed scaling for z
    """
    opacity: float = 0.55
    colormap: str = "viridis"
    vmin: Optional[float] = None
    vmax: Optional[float] = None


@dataclass
class FeatureSelection:
    """
    Payload coming back from JS when selection changes.
    """
    layer_id: str
    feature_ids: List[str] = field(default_factory=list)
    count: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FastPointsStyle:
    """Style for FastPointsLayer (canvas-rendered, index-backed).

    RGBA channels are 0-255.
    
    You can specify colors either as:
    - default_rgba/selected_rgba: RGBA tuples (r, g, b, a) with values 0-255
    - default_color/selected_color: QColor objects or color name strings (e.g., 'Green', 'Red')
    
    If both are specified, the *_color options take precedence.
    """
    radius: float = 3.0
    default_rgba: tuple[int, int, int, int] = (255, 51, 51, 204)
    selected_radius: float = 6.0
    selected_rgba: tuple[int, int, int, int] = (0, 255, 255, 255)
    
    # Optional QColor or color name alternatives
    default_color: Optional[Union[tuple[int, int, int, int], str, Any]] = None
    selected_color: Optional[Union[tuple[int, int, int, int], str, Any]] = None

    def to_js(self) -> dict:
        # Use *_color if provided, otherwise fall back to *_rgba
        default_rgba_final = (
            _normalize_color_to_rgba(self.default_color)
            if self.default_color is not None
            else self.default_rgba
        )
        selected_rgba_final = (
            _normalize_color_to_rgba(self.selected_color)
            if self.selected_color is not None
            else self.selected_rgba
        )
        
        return {
            "radius": float(self.radius),
            "default_rgba": list(default_rgba_final),
            "selected_radius": float(self.selected_radius),
            "selected_rgba": list(selected_rgba_final),
        }


@dataclass(frozen=True)
class FastGeoPointsStyle:
    """Style for FastGeoPointsLayer (points + attached geo ellipses).

    Points are rendered like FastPointsStyle.

    Ellipse stroke/fill RGBA channels are 0-255.
    
    You can specify point colors either as:
    - default_point_rgba/selected_point_rgba: RGBA tuples (r, g, b, a) with values 0-255
    - default_color/selected_color: QColor objects or color name strings (e.g., 'Green', 'Red')
    
    If both are specified, the *_color options take precedence.

    Notes:
      - ellipses_visible toggles drawing of ellipses without hiding points.
      - fill_ellipses defaults to False for performance.
      - min_ellipse_px allows culling very small ellipses.
    """

    # point style
    point_radius: float = 3.0
    default_point_rgba: tuple[int, int, int, int] = (255, 51, 51, 204)
    selected_point_radius: float = 6.0
    selected_point_rgba: tuple[int, int, int, int] = (0, 255, 255, 255)
    
    # Optional QColor or color name alternatives for points
    default_color: Optional[Union[tuple[int, int, int, int], str, Any]] = None
    selected_color: Optional[Union[tuple[int, int, int, int], str, Any]] = None

    # ellipse style
    ellipse_stroke_rgba: tuple[int, int, int, int] = (255, 204, 0, 180)
    ellipse_stroke_width: float = 1.5

    # selected ellipse style (optional override)
    selected_ellipse_stroke_rgba: tuple[int, int, int, int] | None = None
    selected_ellipse_stroke_width: float | None = None
    fill_ellipses: bool = False
    ellipse_fill_rgba: tuple[int, int, int, int] = (255, 204, 0, 40)

    # behavior
    ellipses_visible: bool = True
    min_ellipse_px: float = 0.0
    max_ellipses_per_path: int = 2000
    skip_ellipses_while_interacting: bool = True

    def to_js(self) -> dict:
        # Use *_color if provided, otherwise fall back to *_point_rgba
        default_point_rgba_final = (
            _normalize_color_to_rgba(self.default_color)
            if self.default_color is not None
            else self.default_point_rgba
        )
        selected_point_rgba_final = (
            _normalize_color_to_rgba(self.selected_color)
            if self.selected_color is not None
            else self.selected_point_rgba
        )
        
        return {
            "point_radius": float(self.point_radius),
            "default_point_rgba": list(default_point_rgba_final),
            "selected_point_radius": float(self.selected_point_radius),
            "selected_point_rgba": list(selected_point_rgba_final),
            "ellipse_stroke_rgba": list(self.ellipse_stroke_rgba),
            "ellipse_stroke_width": float(self.ellipse_stroke_width),
            "selected_ellipse_stroke_rgba": (
                list(self.selected_ellipse_stroke_rgba)
                if self.selected_ellipse_stroke_rgba is not None else None
            ),
            "selected_ellipse_stroke_width": (
                float(self.selected_ellipse_stroke_width)
                if self.selected_ellipse_stroke_width is not None else None
            ),
            "fill_ellipses": bool(self.fill_ellipses),
            "ellipse_fill_rgba": list(self.ellipse_fill_rgba),
            "ellipses_visible": bool(self.ellipses_visible),
            "min_ellipse_px": float(self.min_ellipse_px),
            "max_ellipses_per_path": int(self.max_ellipses_per_path),
            "skip_ellipses_while_interacting": bool(self.skip_ellipses_while_interacting),
        }
