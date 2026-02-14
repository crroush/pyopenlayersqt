from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

# Color type: QColor objects, color names, "#RRGGBB", "rgba(...)", or tuples (deprecated)
# Using Any for QColor to avoid hard dependency on PySide6 in type checking
# Note: RGBA tuples are deprecated; prefer QColor objects or color name strings
Color = Union[str, Tuple[int, int, int], Tuple[int, int, int, int], Any]
LatLon = Tuple[float, float]  # (lat, lon) - Public API uses latitude first


@dataclass(frozen=True)
class MeasurementUpdate:
    """Structured payload for distance measurement clicks.

    Attributes:
        point_index: Zero-based index of the clicked measurement point.
        lat: Latitude of the clicked point.
        lon: Longitude of the clicked point.
        segment_distance_m: Distance from previous point to this point in meters.
            ``None`` for the first point.
        cumulative_distance_m: Total path distance up to this point in meters.
    """

    point_index: int
    lat: float
    lon: float
    segment_distance_m: Optional[float]
    cumulative_distance_m: float


def _qcolor_to_rgba(color: Any) -> tuple[int, int, int, int]:
    """Convert a QColor object to an RGBA tuple.
    
    Args:
        color: QColor object from PySide6.QtGui. Note that the type hint uses Any
               to avoid requiring PySide6 as a hard dependency for type checking.
        
    Returns:
        Tuple of (r, g, b, a) with values 0-255.
        
    Raises:
        TypeError: If the input is not a QColor object.
    """
    # Import here to avoid circular dependency and allow models.py to work without Qt
    try:
        from PySide6.QtGui import QColor
        if isinstance(color, QColor):
            return (color.red(), color.green(), color.blue(), color.alpha())
    except ImportError:
        pass
    raise TypeError(f"Expected QColor object, got {type(color)}")


def _is_color_name_string(s: str) -> bool:
    """Check if a string is likely a color name (not hex or CSS).
    
    Args:
        s: String to check
        
    Returns:
        True if the string appears to be a color name, False otherwise.
    """
    # Exclude hex colors (#RRGGBB) and CSS rgba/rgb strings
    return not (s.startswith("#") or s.startswith("rgb"))


def _color_name_to_rgba(color_name: str) -> tuple[int, int, int, int]:
    """Convert a color name (e.g., 'Green', 'Red') to RGBA tuple using QColor.
    
    Args:
        color_name: Color name (e.g., 'Green', 'Red', 'blue')
        
    Returns:
        Tuple of (r, g, b, a) with values 0-255.
        
    Raises:
        ValueError: If PySide6 is not available, Qt cannot initialize, or color name is invalid.
                   In this case, use RGBA tuples (r, g, b, a) instead.
    """
    try:
        from PySide6.QtGui import QColor
        qcolor = QColor(color_name)
        if qcolor.isValid():
            return (qcolor.red(), qcolor.green(), qcolor.blue(), qcolor.alpha())
        raise ValueError(
            f"Invalid color name: '{color_name}'. "
            f"Use RGBA tuples like (255, 0, 0, 255) instead."
        )
    except (ImportError, RuntimeError) as e:
        # RuntimeError can occur if Qt can't initialize (e.g., no display)
        raise ValueError(
            f"Cannot convert color name '{color_name}': PySide6 is not available "
            f"or Qt cannot initialize ({type(e).__name__}: {e}). "
            f"Use RGBA tuples like (255, 0, 0, 255) instead."
        ) from e


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
    except (ImportError, RuntimeError):
        pass

    # Handle string inputs
    if isinstance(c, str):
        # Try to interpret as color name using QColor
        try:
            from PySide6.QtGui import QColor
            qcolor = QColor(c)
            if qcolor.isValid() and _is_color_name_string(c):
                # It's a valid color name like 'Green', convert to tuple
                c = (qcolor.red(), qcolor.green(), qcolor.blue(), qcolor.alpha())
            else:
                # It's a hex color or CSS string, handle below
                pass
        except (ImportError, RuntimeError):
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
    
    Colors can be specified as:
    - Hex string: "#ff3333"
    - CSS string: "rgba(255, 51, 51, 0.8)"
    - RGB tuple: (255, 51, 51)
    - RGBA tuple: (255, 51, 51, 204)
    - QColor object: QColor("red") or QColor(255, 0, 0)
    - Color name: "red", "Green", "steelblue"
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
    
    Colors can be specified as:
    - Hex string: "#00aaff"
    - CSS string: "rgba(0, 170, 255, 0.95)"
    - RGB tuple: (0, 170, 255)
    - RGBA tuple: (0, 170, 255, 242)
    - QColor object: QColor("blue") or QColor(0, 170, 255)
    - Color name: "blue", "steelblue", "cyan"
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
    
    Colors can be specified as:
    - Hex string: "#00aaff"
    - CSS string: "rgba(0, 170, 255, 0.95)"
    - RGB tuple: (0, 170, 255)
    - RGBA tuple: (0, 170, 255, 242)
    - QColor object: QColor("blue") or QColor(0, 170, 255)
    - Color name: "blue", "Green", "purple"
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
    
    Colors can be specified as:
    - Hex string: "#ffcc00"
    - CSS string: "rgba(255, 204, 0, 0.95)"
    - RGB tuple: (255, 204, 0)
    - RGBA tuple: (255, 204, 0, 242)
    - QColor object: QColor("yellow") or QColor(255, 204, 0)
    - Color name: "yellow", "gold", "orange"
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
    default_color: Optional[Union[str, Any]] = None
    selected_color: Optional[Union[str, Any]] = None

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

    You can specify colors using:
    - Point colors: default_color/selected_color (QColor objects or color names, recommended)
    - Point colors (legacy): default_point_rgba/selected_point_rgba (RGBA tuples, deprecated)
    - Ellipse stroke: ellipse_stroke_color (QColor or color name, recommended)
    - Ellipse stroke (legacy): ellipse_stroke_rgba (RGBA tuple, deprecated)
    - Ellipse fill: ellipse_fill_color (QColor or color name, recommended)
    - Ellipse fill (legacy): ellipse_fill_rgba (RGBA tuple, deprecated)
    - Selected ellipse stroke: selected_ellipse_stroke_color (QColor or color name, recommended)
    - Selected ellipse stroke (legacy): selected_ellipse_stroke_rgba (RGBA tuple, deprecated)
    
    If both are specified, the *_color options take precedence.

    Notes:
      - ellipses_visible toggles drawing of unselected ellipses without hiding points.
      - selected_ellipses_visible toggles drawing of selected ellipses independently.
      - fill_ellipses defaults to False for performance.
      - min_ellipse_px allows culling very small ellipses.
    """

    # point style
    point_radius: float = 3.0
    default_point_rgba: tuple[int, int, int, int] = (255, 51, 51, 204)
    selected_point_radius: float = 6.0
    selected_point_rgba: tuple[int, int, int, int] = (0, 255, 255, 255)

    # Optional QColor or color name alternatives for points
    default_color: Optional[Union[str, Any]] = None
    selected_color: Optional[Union[str, Any]] = None

    # ellipse style
    ellipse_stroke_rgba: tuple[int, int, int, int] = (255, 204, 0, 180)
    ellipse_stroke_width: float = 1.5

    # Optional QColor or color name alternative for ellipse stroke
    ellipse_stroke_color: Optional[Union[str, Any]] = None

    # selected ellipse style (optional override)
    selected_ellipse_stroke_rgba: tuple[int, int, int, int] | None = None
    selected_ellipse_stroke_width: float | None = None

    # Optional QColor or color name alternative for selected ellipse stroke
    selected_ellipse_stroke_color: Optional[Union[str, Any]] = None

    fill_ellipses: bool = False
    ellipse_fill_rgba: tuple[int, int, int, int] = (255, 204, 0, 40)

    # Optional QColor or color name alternative for ellipse fill
    ellipse_fill_color: Optional[Union[str, Any]] = None

    # behavior
    ellipses_visible: bool = True
    selected_ellipses_visible: bool = True
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

        # Use ellipse_stroke_color if provided, else ellipse_stroke_rgba
        ellipse_stroke_rgba_final = (
            _normalize_color_to_rgba(self.ellipse_stroke_color)
            if self.ellipse_stroke_color is not None
            else self.ellipse_stroke_rgba
        )

        # Use selected_ellipse_stroke_color if provided, else _rgba fallback
        selected_ellipse_stroke_rgba_final = None
        if self.selected_ellipse_stroke_color is not None:
            selected_ellipse_stroke_rgba_final = _normalize_color_to_rgba(
                self.selected_ellipse_stroke_color
            )
        elif self.selected_ellipse_stroke_rgba is not None:
            selected_ellipse_stroke_rgba_final = (
                self.selected_ellipse_stroke_rgba
            )

        # Use ellipse_fill_color if provided, otherwise fall back to ellipse_fill_rgba
        ellipse_fill_rgba_final = (
            _normalize_color_to_rgba(self.ellipse_fill_color)
            if self.ellipse_fill_color is not None
            else self.ellipse_fill_rgba
        )

        return {
            "point_radius": float(self.point_radius),
            "default_point_rgba": list(default_point_rgba_final),
            "selected_point_radius": float(self.selected_point_radius),
            "selected_point_rgba": list(selected_point_rgba_final),
            "ellipse_stroke_rgba": list(ellipse_stroke_rgba_final),
            "ellipse_stroke_width": float(self.ellipse_stroke_width),
            "selected_ellipse_stroke_rgba": (
                list(selected_ellipse_stroke_rgba_final)
                if selected_ellipse_stroke_rgba_final is not None else None
            ),
            "selected_ellipse_stroke_width": (
                float(self.selected_ellipse_stroke_width)
                if self.selected_ellipse_stroke_width is not None else None
            ),
            "fill_ellipses": bool(self.fill_ellipses),
            "ellipse_fill_rgba": list(ellipse_fill_rgba_final),
            "ellipses_visible": bool(self.ellipses_visible),
            "selected_ellipses_visible": bool(self.selected_ellipses_visible),
            "min_ellipse_px": float(self.min_ellipse_px),
            "max_ellipses_per_path": int(self.max_ellipses_per_path),
            "skip_ellipses_while_interacting": bool(self.skip_ellipses_while_interacting),
        }
