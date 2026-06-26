from __future__ import annotations

from dataclasses import replace
import os
import time
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np

from .utils import clamp
from .models import (
    CircleStyle,
    EllipseStyle,
    IconStyle,
    LatLon,
    PointStyle,
    PolygonStyle,
    RasterStyle,
    WMSOptions,
    TileLayerOptions,
)


def _qcolor_to_rgba(color: Any) -> tuple[int, int, int, int]:
    """Convert a QColor object to an RGBA tuple.
    
    Args:
        color: QColor object from PySide6.QtGui
        
    Returns:
        Tuple of (r, g, b, a) with values 0-255.
    """
    # Import here to avoid circular dependency and allow layers.py to work without Qt
    try:
        from PySide6.QtGui import QColor
        if isinstance(color, QColor):
            return (color.red(), color.green(), color.blue(), color.alpha())
    except ImportError:
        pass
    raise TypeError(f"Expected QColor object, got {type(color)}")


def _normalize_color(
    color: Union[tuple[int, int, int, int], str, Any]
) -> tuple[int, int, int, int]:
    """Normalize a color to RGBA tuple format.

    Accepts:
    - RGBA tuple: (r, g, b, a) with values 0-255
    - QColor object from PySide6.QtGui
    - Color name string (e.g., 'Green', 'Red', 'blue')
    
    Args:
        color: RGBA tuple, QColor object, or color name string
        
    Returns:
        Tuple of (r, g, b, a) with values 0-255.
        
    Raises:
        TypeError: If color is not a recognized type.
        ValueError: If color name is invalid or PySide6 is not available.
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
        try:
            from PySide6.QtGui import QColor
            qcolor = QColor(color)
            if qcolor.isValid():
                return (qcolor.red(), qcolor.green(), qcolor.blue(), qcolor.alpha())
            raise ValueError(
                f"Invalid color name: '{color}'. "
                f"Use RGBA tuples like (255, 0, 0, 255) instead."
            )
        except (ImportError, RuntimeError) as e:
            # RuntimeError can occur if Qt can't initialize (e.g., no display)
            raise ValueError(
                f"Cannot convert color name '{color}': PySide6 is not available "
                f"or Qt cannot initialize ({type(e).__name__}: {e}). "
                f"Use RGBA tuples like (255, 0, 0, 255) instead."
            ) from e

    raise TypeError(
        f"Color must be an RGBA tuple (r, g, b, a), a QColor object, "
        f"or a color name string, got {type(color)}"
    )




def _latlon_chunk_to_lonlat_list(coords: Sequence[LatLon]) -> list[list[float]]:
    arr = np.asarray(coords, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError("coords must be a sequence of (lat, lon) pairs")
    return arr[:, [1, 0]].tolist()


def _perf_enabled() -> bool:
    return (
        os.environ.get("PYOPENLAYERSQT_BENCH", "") == "1"
        or os.environ.get("PYOPENLAYERSQT_PERF", "") == "1"
    )


def _perf_print(payload: dict[str, Any]) -> None:
    if _perf_enabled():
        print("PERF:", payload, flush=True)



def _resolve_colormap_rgba(
    values: Sequence[float],
    cmap: Union[str, Any] = "viridis",
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
) -> List[tuple[int, int, int, int]]:
    """Map scalar values to RGBA colors using a matplotlib colormap."""
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError("values must be a non-empty 1D sequence")

    lo = float(np.min(arr) if vmin is None else vmin)
    hi = float(np.max(arr) if vmax is None else vmax)
    if hi < lo:
        raise ValueError("vmax must be >= vmin")

    if hi == lo:
        norm = np.zeros_like(arr, dtype=float)
    else:
        norm = np.clip((arr - lo) / (hi - lo), 0.0, 1.0)

    try:
        import matplotlib.cm as mcm
    except ImportError as e:
        raise ImportError(
            "matplotlib is required for colormap-based line coloring. "
            "Install matplotlib or pass explicit segment colors."
        ) from e

    cmap_obj = mcm.get_cmap(cmap) if isinstance(cmap, str) else cmap
    rgba = np.asarray(cmap_obj(norm))
    out = np.clip(np.rint(rgba * 255.0), 0, 255).astype(np.uint8)
    return [tuple(map(int, row)) for row in out]
def _pack_rgba_colors(colors: List[Union[tuple[int, int, int, int], str, Any]]) -> List[int]:
    """Convert list of colors to packed 32-bit integers.
    
    Accepts colors as:
    - RGBA tuples: (r, g, b, a) with values 0-255
    - QColor objects from PySide6.QtGui
    - Color name strings (e.g., 'Green', 'Red')
    
    Args:
        colors: List of RGBA tuples, QColor objects, or color name strings.
    
    Returns:
        List of packed 32-bit integers.
    """
    packed: List[int] = []
    for color in colors:
        r, g, b, a = _normalize_color(color)
        packed.append(
            ((r & 255) << 24) | ((g & 255) << 16) | ((b & 255) << 8) | (a & 255)
        )
    return packed


def _expand_gradient_coords(
    coords: Sequence[LatLon], interpolate_steps: int
) -> tuple[List[LatLon], int]:
    coord_pairs = list(coords)
    seg_count = len(coord_pairs) - 1
    if interpolate_steps == 1:
        return coord_pairs, seg_count

    expanded: List[LatLon] = [coord_pairs[0]]
    for i in range(seg_count):
        lat0, lon0 = coord_pairs[i]
        lat1, lon1 = coord_pairs[i + 1]
        for step in range(1, interpolate_steps + 1):
            t = step / float(interpolate_steps)
            expanded.append((lat0 + (lat1 - lat0) * t, lon0 + (lon1 - lon0) * t))
    return expanded, seg_count


def _rendered_values_from_input(
    values: Optional[Sequence[float]],
    coord_pairs: Sequence[LatLon],
    seg_count: int,
    interpolate_steps: int,
) -> List[float]:
    if values is None:
        return []

    raw_vals = np.asarray(values, dtype=float)
    if raw_vals.size == len(coord_pairs):
        vertex_values = [float(v) for v in raw_vals]
    elif raw_vals.size == seg_count:
        vertex_values = [0.0] * len(coord_pairs)
        vertex_values[0] = float(raw_vals[0])
        vertex_values[-1] = float(raw_vals[-1])
        for i in range(1, len(coord_pairs) - 1):
            vertex_values[i] = 0.5 * (float(raw_vals[i - 1]) + float(raw_vals[i]))
    else:
        raise ValueError(
            "values length must equal len(coords)-1 (per segment) "
            "or len(coords) (per vertex)"
        )

    if interpolate_steps == 1:
        return [
            0.5 * (vertex_values[i] + vertex_values[i + 1])
            for i in range(seg_count)
        ]

    rendered_values: List[float] = []
    for i in range(seg_count):
        v0 = float(vertex_values[i])
        v1 = float(vertex_values[i + 1])
        for step in range(1, interpolate_steps + 1):
            tmid = (step - 0.5) / float(interpolate_steps)
            rendered_values.append(v0 + (v1 - v0) * tmid)
    return rendered_values


def _resolve_gradient_segment_colors(
    segment_colors: Optional[Sequence[Union[tuple[int, int, int, int], str, Any]]],
    rendered_values: Sequence[float],
    seg_count: int,
    rendered_seg_count: int,
    interpolate_steps: int,
    cmap: Union[str, Any],
    vmin: Optional[float],
    vmax: Optional[float],
    values: Optional[Sequence[float]],
) -> List[tuple[int, int, int, int]]:
    if segment_colors is None:
        if values is None:
            raise ValueError("values is required when segment_colors is not provided")
        return _resolve_colormap_rgba(rendered_values, cmap=cmap, vmin=vmin, vmax=vmax)

    if len(segment_colors) == rendered_seg_count:
        return [_normalize_color(c) for c in segment_colors]

    if len(segment_colors) == seg_count:
        rgba_colors: List[tuple[int, int, int, int]] = []
        for color in segment_colors:
            rgba = _normalize_color(color)
            rgba_colors.extend([rgba] * interpolate_steps)
        return rgba_colors

    raise ValueError(
        "segment_colors length must equal len(coords)-1 "
        "(one per input segment) or rendered segment count"
    )


class BaseLayer:
    """Base class for all layer types.

    Provides common functionality for layer management including opacity,
    visibility, selectability, and removal operations.
    """

    # Subclasses can override this to customize message type prefixes
    _layer_type_prefix: Optional[str] = None

    def __init__(self, widget: Any, layer_id: str, name: str = ""):
        """Initialize a layer.

        Args:
            widget: The map widget or widget instance.
            layer_id: Unique identifier for this layer.
            name: Optional human-readable name (defaults to layer_id).
        """
        self._map_widget = widget
        self.id = layer_id
        self.name = name or layer_id

    def remove(self) -> None:
        """Remove this layer from the map."""
        self._map_widget._send({"type": "layer.remove", "layer_id": self.id})

    def set_opacity(self, opacity: float) -> None:
        """Set the opacity of this layer.

        Args:
            opacity: Opacity value between 0.0 (transparent) and 1.0 (opaque).
        """
        msg_type = (
            f"{self._layer_type_prefix}.set_opacity"
            if self._layer_type_prefix
            else "layer.opacity"
        )
        self._map_widget._send(
            {"type": msg_type, "layer_id": self.id, "opacity": clamp(opacity)}
        )

    def set_visible(self, visible: bool) -> None:
        """Set the visibility of this layer.

        Args:
            visible: True to show the layer, False to hide it.
        """
        if not self._layer_type_prefix:
            raise NotImplementedError(
                "set_visible requires _layer_type_prefix to be set"
            )
        self._map_widget._send(
            {
                "type": f"{self._layer_type_prefix}.set_visible",
                "layer_id": self.id,
                "visible": bool(visible),
            }
        )

    def set_selectable(self, selectable: bool) -> None:
        """Set whether features in this layer can be selected.

        Args:
            selectable: True to allow feature selection, False to disable.
        """
        if not self._layer_type_prefix:
            raise NotImplementedError(
                "set_selectable requires _layer_type_prefix to be set"
            )
        self._map_widget._send(
            {
                "type": f"{self._layer_type_prefix}.set_selectable",
                "layer_id": self.id,
                "selectable": bool(selectable),
            }
        )

    def clear(self) -> None:
        """Clear all features from this layer."""
        if not self._layer_type_prefix:
            raise NotImplementedError(
                "clear requires _layer_type_prefix to be set"
            )
        self._map_widget._send({"type": f"{self._layer_type_prefix}.clear", "layer_id": self.id})


class VectorLayer(BaseLayer):
    """A layer that can hold points/polygons/circles/ellipses/lines as vector features.

    Supports rich styling with per-feature properties and various geometry types.
    """

    _layer_type_prefix = "vector"

    def remove_features(self, feature_ids: Sequence[str]) -> None:
        """Remove vector features by id."""
        self._map_widget._send(
            {
                "type": "vector.remove_features",
                "layer_id": self.id,
                "feature_ids": [str(x) for x in feature_ids],
            }
        )

    def update_feature_styles(
        self,
        feature_ids: Sequence[str],
        styles: Sequence[
            PointStyle | IconStyle | PolygonStyle | CircleStyle | EllipseStyle
        ],
    ) -> None:
        """Update styles for specific features by ID.

        This allows changing colors and other style properties of selected or any features.

        Args:
            feature_ids: List of feature IDs to update.
            styles: List of style objects, one per feature ID. Use the appropriate
                    style type for each feature (PointStyle, IconStyle, PolygonStyle, etc.).
        """
        if len(feature_ids) != len(styles):
            raise ValueError("feature_ids and styles must have the same length")

        fids = [str(x) for x in feature_ids]
        styles_js = [s.to_js() for s in styles]

        self._map_widget._send(
            {
                "type": "vector.update_styles",
                "layer_id": self.id,
                "feature_ids": fids,
                "styles": styles_js,
            }
        )

    def add_points(
        self,
        coords: Sequence[LatLon],
        ids: Optional[Sequence[str]] = None,
        style: Optional[PointStyle | IconStyle] = None,
        properties: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> None:
        """Add point features to the layer.

        Args:
            coords: Sequence of (lat, lon) tuples for each point.
            ids: Optional sequence of feature IDs. Auto-generated if not provided.
            style: Point or icon styling. Uses default PointStyle if not provided.
            properties: Optional properties dict for each point.
        """
        style = style or PointStyle()
        ids = list(ids) if ids is not None else [f"pt{i}" for i in range(len(coords))]
        props = (
            list(properties)
            if properties is not None
            else [{} for _ in range(len(coords))]
        )
        # Swap lat,lon (public API) to lon,lat (internal format)
        self._map_widget._send(
            {
                "type": "vector.add_points",
                "layer_id": self.id,
                "coords": [[float(lon), float(lat)] for (lat, lon) in coords],
                "ids": list(ids),
                "style": style.to_js(),
                "properties": props,
            }
        )

    def add_icon_points(
        # pylint: disable=too-many-arguments
        self,
        coords: Sequence[LatLon],
        icon: Any = None,
        selected_icon: Any = None,
        ids: Optional[Sequence[str]] = None,
        style: Optional[IconStyle] = None,
        properties: Optional[Sequence[Dict[str, Any]]] = None,
        scale: float = 1.0,
        opacity: float = 1.0,
        anchor: tuple[float, float] = (0.5, 1.0),
        rotation_deg: float = 0.0,
        rotate_with_view: bool = False,
        cross_origin: Optional[str] = None,
    ) -> None:
        """Add point features rendered with a custom icon.

        Args:
            coords: Sequence of (lat, lon) tuples for each point.
            icon: URL, local image path, data URI, or image bytes. Supported byte
                containers are bytes, bytearray, memoryview, and QByteArray. Local
                files and bytes are cached and served automatically to the embedded
                browser.
            selected_icon: Optional alternate icon to use while the feature is
                selected. Accepts the same input forms as icon.
            ids: Optional sequence of feature IDs. Auto-generated if not provided.
            style: Optional advanced IconStyle. Most callers can use the direct
                scale/opacity/anchor/rotation_deg arguments instead.
            properties: Optional properties dict for each icon point.
            scale: Icon scale multiplier.
            opacity: Icon opacity from 0.0 to 1.0.
            anchor: Icon anchor as fractions by default. ``(0.5, 1.0)`` pins the
                bottom center of the icon to the feature coordinate.
            rotation_deg: Clockwise degrees from true north (up on an unrotated map). Use
                ``rotate_with_view=True`` when the marker should stay aligned with
                map north if the view rotates.
            rotate_with_view: If True, icon rotates with the map view.
            cross_origin: Optional cross-origin setting for remote images.
        """
        icon_style = style or IconStyle(
            scale=scale,
            opacity=opacity,
            anchor=anchor,
            rotation_deg=rotation_deg,
            rotate_with_view=rotate_with_view,
            cross_origin=cross_origin,
        )

        icon_value = icon if icon is not None else icon_style.icon_src
        if not icon_value:
            raise ValueError("icon must be a URL, local image path, data URI, or bytes-like value")

        selected_icon_value = (
            selected_icon
            if selected_icon is not None
            else icon_style.selected_icon_src
        )
        icon_style = replace(
            icon_style,
            icon_src=self._map_widget._icon_to_src(icon_value),
            selected_icon_src=(
                self._map_widget._icon_to_src(selected_icon_value)
                if selected_icon_value else None
            ),
        )
        self.add_points(
            coords=coords,
            ids=ids,
            style=icon_style,
            properties=properties,
        )

    def add_polygon(
        self,
        ring: Sequence[LatLon],
        feature_id: str = "poly0",
        style: Optional[PolygonStyle] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a polygon feature to the layer.

        Args:
            ring: Sequence of (lat, lon) tuples defining the polygon boundary.
            feature_id: ID for this polygon feature.
            style: Polygon styling. Uses default if not provided.
            properties: Optional properties dict for this feature.
        """
        style = style or PolygonStyle()
        # Swap lat,lon (public API) to lon,lat (internal format)
        self._map_widget._send(
            {
                "type": "vector.add_polygon",
                "layer_id": self.id,
                "ring": [[float(lon), float(lat)] for (lat, lon) in ring],
                "id": feature_id,
                "style": style.to_js(),
                "properties": properties or {},
            }
        )

    def add_circle(
        self,
        center: LatLon,
        radius_m: float,
        feature_id: str = "circle0",
        style: Optional[CircleStyle] = None,
        properties: Optional[Dict[str, Any]] = None,
        segments: int = 72,
    ) -> None:
        """Add a circle feature to the layer.

        Args:
            center: Center point as (lat, lon) tuple.
            radius_m: Radius in meters.
            feature_id: ID for this circle feature.
            style: Circle styling. Uses default if not provided.
            properties: Optional properties dict for this feature.
            segments: Number of segments to approximate the circle.
        """
        style = style or CircleStyle()
        # Swap lat,lon (public API) to lon,lat (internal format)
        lat, lon = center
        self._map_widget._send(
            {
                "type": "vector.add_circle",
                "layer_id": self.id,
                "center": [float(lon), float(lat)],
                "radius_m": float(radius_m),
                "id": feature_id,
                "style": style.to_js(),
                "properties": properties or {},
                "segments": int(segments),
            }
        )

    def add_line(
        self,
        coords: Sequence[LatLon],
        feature_id: str = "line0",
        style: Optional[PolygonStyle] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a polyline (non-closed) feature to this vector layer.

        Args:
            coords: Sequence of (lat, lon) tuples describing the line vertices in order.
            feature_id: The feature ID to assign.
            style: A PolygonStyle (uses stroke_* attributes) or None for defaults.
            properties: Optional dict of properties to attach to the feature.
        """
        style = style or PolygonStyle()
        # Swap lat,lon (public API) to lon,lat (internal format)
        self._map_widget._send(
            {
                "type": "vector.add_line",
                "layer_id": self.id,
                "coords": [[float(lon), float(lat)] for (lat, lon) in coords],
                "id": feature_id,
                "style": style.to_js(),
                "properties": properties or {},
            }
        )

    def add_gradient_line(
        # pylint: disable=too-many-arguments
        self,
        coords: Sequence[LatLon],
        values: Optional[Sequence[float]] = None,
        feature_id: str = "gradient_line0",
        style: Optional[PolygonStyle] = None,
        cmap: Union[str, Any] = "viridis",
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
        segment_colors: Optional[Sequence[Union[tuple[int, int, int, int], str, Any]]] = None,
        properties: Optional[Dict[str, Any]] = None,
        interpolate_steps: int = 64,
    ) -> None:
        """Add a polyline rendered with per-segment colors (useful for speed tracks).

        Args:
            coords: Sequence of (lat, lon) vertices. Must contain at least 2 points.
            values: Optional scalar values used for colormap mapping. Supports
                either per-segment values (len(coords)-1) or per-vertex values
                (len(coords)). Values are converted to per-vertex anchors and
                smoothly interpolated when ``interpolate_steps > 1``.
            feature_id: Base ID for created segment features.
            style: Base stroke style (stroke_width and opacity are respected).
            cmap: Matplotlib colormap name/object used when segment_colors is None.
            vmin: Lower normalization bound for values.
            vmax: Upper normalization bound for values.
            segment_colors: Optional explicit colors (one per rendered segment).
            properties: Optional feature properties copied to every segment.
            interpolate_steps: Number of sub-segments per original segment for
                gradient rendering (applies to both per-segment and per-vertex values).
                Higher values make smoother gradients; default is 64 for visibly
                continuous ramps on typical routes.
        """
        if len(coords) < 2:
            raise ValueError("coords must contain at least 2 points")
        if interpolate_steps < 1:
            raise ValueError("interpolate_steps must be >= 1")

        coord_pairs = list(coords)
        expanded_coords, seg_count = _expand_gradient_coords(
            coord_pairs, int(interpolate_steps)
        )
        rendered_seg_count = len(expanded_coords) - 1

        rendered_values = _rendered_values_from_input(
            values=values,
            coord_pairs=coord_pairs,
            seg_count=seg_count,
            interpolate_steps=int(interpolate_steps),
        )

        rgba_colors = _resolve_gradient_segment_colors(
            segment_colors=segment_colors,
            rendered_values=rendered_values,
            seg_count=seg_count,
            rendered_seg_count=rendered_seg_count,
            interpolate_steps=int(interpolate_steps),
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            values=values,
        )

        style = style or PolygonStyle()

        self._map_widget._send(
            {
                "type": "vector.add_gradient_line",
                "layer_id": self.id,
                "coords": [[float(lon), float(lat)] for (lat, lon) in expanded_coords],
                "values": rendered_values if values is not None else [],
                "segment_colors": _pack_rgba_colors(rgba_colors),
                "id": feature_id,
                "style": style.to_js(),
                "properties": properties or {},
            }
        )

    def add_ellipse(
        self,
        center: LatLon,
        sma_m: float,
        smi_m: float,
        tilt_deg: float,
        feature_id: str = "ell0",
        style: Optional[EllipseStyle] = None,
        properties: Optional[Dict[str, Any]] = None,
        segments: int = 96,
    ) -> None:
        """Add an ellipse feature to the layer.

        Args:
            center: Center point as (lat, lon) tuple.
            sma_m: Semi-major axis in meters.
            smi_m: Semi-minor axis in meters.
            tilt_deg: Tilt angle in degrees clockwise from true north.
            feature_id: ID for this ellipse feature.
            style: Ellipse styling. Uses default if not provided.
            properties: Optional properties dict for this feature.
            segments: Number of segments to approximate the ellipse.
        """
        style = style or EllipseStyle()
        # Swap lat,lon (public API) to lon,lat (internal format)
        lat, lon = center
        self._map_widget._send(
            {
                "type": "vector.add_ellipse",
                "layer_id": self.id,
                "center": [float(lon), float(lat)],
                "sma_m": float(sma_m),
                "smi_m": float(smi_m),
                "tilt_deg": float(tilt_deg),
                "id": feature_id,
                "style": style.to_js(),
                "properties": properties or {},
                "segments": int(segments),
            }
        )


class WMSLayer(BaseLayer):
    _layer_type_prefix = "wms"

    def __init__(self, widget: Any, layer_id: str, opt: WMSOptions, name: str = ""):
        super().__init__(widget, layer_id, name=name or layer_id)
        self.opt = opt

    def set_params(self, params: Dict[str, Any]) -> None:
        self.opt = WMSOptions(
            url=self.opt.url, params=dict(params), opacity=self.opt.opacity
        )
        self._map_widget._send(
            {"type": "wms.set_params", "layer_id": self.id, "params": dict(params)}
        )


class TileLayer(BaseLayer):
    _layer_type_prefix = "tile"

    def __init__(
        self, widget: Any, layer_id: str, opt: TileLayerOptions, name: str = ""
    ):
        super().__init__(widget, layer_id, name=name or layer_id)
        self.opt = opt

    def set_url(self, url: str) -> None:
        self.opt = TileLayerOptions(
            url=str(url), opacity=self.opt.opacity, attribution=self.opt.attribution
        )
        self._map_widget._send(
            {
                "type": "tile.set_url",
                "layer_id": self.id,
                "url": str(url),
                "attribution": self.opt.attribution,
            }
        )


class RasterLayer(BaseLayer):
    """Image overlay layer (PNG served by the widget HTTP server).

    Bounds are specified as (lat, lon) tuples in the public API.
    """

    def __init__(
        self,
        widget: Any,
        layer_id: str,
        url: str,
        bounds: List[LatLon],
        style: RasterStyle,
        name: str = "",
    ):
        super().__init__(widget, layer_id, name=name or layer_id)
        self.url = url
        self.bounds = bounds  # [(lat, lon), (lat, lon)] - SW and NE corners
        self.style = style

    def set_image(self, image: Union[str, bytes, bytearray], bounds: List[LatLon]) -> None:
        """Update the raster image.

        Args:
            image: URL/path/server path ("/_overlays/...") or raw PNG bytes.
            bounds: Two (lat, lon) tuples defining SW and NE corners.
        """
        url = self._map_widget._ensure_overlay_url(image)
        self.url = url
        self.bounds = bounds
        # Swap lat,lon (public API) to lon,lat (internal format)
        self._map_widget._send(
            {
                "type": "raster.set_image",
                "layer_id": self.id,
                "url": url,
                "bounds": [[float(lon), float(lat)] for lat, lon in bounds],
            }
        )

    def set_style(self, style: RasterStyle) -> None:
        self.style = style
        self.set_opacity(style.opacity)


class FastPointsLayer(BaseLayer):
    """High-volume point layer (IDs-only selection).

    Backed by a JS-side spatial grid index + canvas renderer.
    No per-point ol.Feature objects.

    Coordinates are specified as (lat, lon) tuples in the public API.
    """

    _layer_type_prefix = "fast_points"

    def __init__(
        self, map_widget: "OLMapWidget", layer_id: str, name: str = ""
    ) -> None:
        super().__init__(map_widget, layer_id, name)

    def add_points(
        self,
        coords: list[tuple[float, float]],
        ids: list[str] | None = None,
        colors_rgba: list[Union[tuple[int, int, int, int], Any]] | None = None,
        chunk_size: int = 50000,
        redraw: bool = True,
    ) -> None:
        """Add points to the layer.

        Args:
            coords: List of (lat, lon) tuples for each point.
            ids: Optional list of feature IDs. Auto-generated if not provided.
            colors_rgba: Optional list of colors. Each color can be either:
                - RGBA tuple: (r, g, b, a) with values 0-255
                - QColor object from PySide6.QtGui
            chunk_size: Number of points per chunk to avoid large JSON payloads.
            redraw: Whether to request a redraw after the final chunk is sent.
        """
        n = len(coords)
        if n == 0:
            return
        if ids is not None and len(ids) != n:
            raise ValueError("ids must have the same length as coords")
        if colors_rgba is not None and len(colors_rgba) != n:
            raise ValueError("colors_rgba must have the same length as coords")

        # Chunking avoids huge JSON payloads that can stall the JS thread.
        if chunk_size <= 0:
            chunk_size = n

        add_start = time.perf_counter()
        chunk_count = 0
        for start in range(0, n, chunk_size):
            chunk_start = time.perf_counter()
            end = min(n, start + chunk_size)
            # Swap lat,lon (public API) to lon,lat (internal format)
            convert_start = time.perf_counter()
            coords_chunk = _latlon_chunk_to_lonlat_list(coords[start:end])
            convert_ms = (time.perf_counter() - convert_start) * 1000.0

            msg: dict = {
                "type": "fast_points.add_points",
                "layer_id": self.id,
                "coords": coords_chunk,
                "redraw": bool(redraw and end == n),
            }
            if ids is not None:
                msg["ids"] = ids[start:end]
            if colors_rgba is not None:
                pack_start = time.perf_counter()
                msg["colors"] = _pack_rgba_colors(colors_rgba[start:end])
                pack_ms = (time.perf_counter() - pack_start) * 1000.0
            else:
                pack_ms = 0.0
            send_start = time.perf_counter()
            self._map_widget._send(msg)
            send_ms = (time.perf_counter() - send_start) * 1000.0
            chunk_count += 1
            _perf_print(
                {
                    "side": "python",
                    "operation": "fast_points_add_points_chunk",
                    "layer_id": self.id,
                    "chunk_index": chunk_count,
                    "start": start,
                    "end": end,
                    "point_count": end - start,
                    "times": {
                        "coords_convert_ms": round(convert_ms, 2),
                        "color_pack_ms": round(pack_ms, 2),
                        "send_enqueue_ms": round(send_ms, 2),
                        "chunk_total_ms": round(
                            (time.perf_counter() - chunk_start) * 1000.0, 2
                        ),
                    },
                }
            )
        _perf_print(
            {
                "side": "python",
                "operation": "fast_points_add_points_total",
                "layer_id": self.id,
                "point_count": n,
                "chunk_count": chunk_count,
                "elapsed_ms": round((time.perf_counter() - add_start) * 1000.0, 2),
            }
        )

    def redraw(self) -> None:
        """Request a redraw of the fast-points layer."""
        self._map_widget._send({"type": "fast_points.redraw", "layer_id": self.id})

    def remove_points(self, feature_ids: Sequence[str]) -> None:
        """Remove fast points by id (marks deleted in JS)."""
        # Send both 'feature_ids' and 'ids' for compatibility with any older/newer JS.
        fids = [str(x) for x in feature_ids]
        self._map_widget._send(
            {
                "type": "fast_points.remove_ids",
                "layer_id": self.id,
                "feature_ids": fids,
                "ids": fids,
            }
        )

    def hide_features(self, feature_ids: Sequence[str]) -> None:
        """Hide features by id (temporarily hide from view; can be unhidden)."""
        fids = [str(x) for x in feature_ids]
        self._map_widget._send(
            {
                "type": "fast_points.hide_ids",
                "layer_id": self.id,
                "feature_ids": fids,
                "ids": fids,
            }
        )

    def show_features(self, feature_ids: Sequence[str]) -> None:
        """Show previously hidden features by id."""
        fids = [str(x) for x in feature_ids]
        self._map_widget._send(
            {
                "type": "fast_points.show_ids",
                "layer_id": self.id,
                "feature_ids": fids,
                "ids": fids,
            }
        )

    def show_all_features(self) -> None:
        """Show all hidden features (reset filter)."""
        self._map_widget._send(
            {
                "type": "fast_points.show_all",
                "layer_id": self.id,
            }
        )

    def set_colors(
        self,
        feature_ids: Sequence[str],
        colors_rgba: list[Union[tuple[int, int, int, int], Any]],
    ) -> None:
        """Update colors for specific features by ID.

        This allows changing colors of selected or any other features.

        Args:
            feature_ids: List of feature IDs to update.
            colors_rgba: List of colors, one per feature ID. Each color can be either:
                - RGBA tuple: (r, g, b, a) with values 0-255
                - QColor object from PySide6.QtGui
        """
        if len(feature_ids) != len(colors_rgba):
            raise ValueError("feature_ids and colors_rgba must have the same length")

        fids = [str(x) for x in feature_ids]
        packed = _pack_rgba_colors(colors_rgba)

        self._map_widget._send(
            {
                "type": "fast_points.set_colors",
                "layer_id": self.id,
                "feature_ids": fids,
                "colors": packed,
            }
        )



class FastGeoPointsLayer(BaseLayer):
    """High-volume geolocation layer: points with attached uncertainty ellipses.

    Each point has:
      - lat/lon (specified as (lat, lon) tuple in public API)
      - sma_m, smi_m (meters)
      - tilt_deg clockwise from true north

    Rendering is canvas-based with a grid index (like FastPointsLayer).
    Ellipses can be toggled on/off independently of points.
    """

    _layer_type_prefix = "fast_geopoints"

    def __init__(self, map_widget: "OLMapWidget", layer_id: str, name: str = "") -> None:
        super().__init__(map_widget, layer_id, name)

    def add_points_with_ellipses(
        self,
        coords: list[tuple[float, float]],
        sma_m: list[float],
        smi_m: list[float],
        tilt_deg: list[float],
        ids: list[str] | None = None,
        colors_rgba: list[Union[tuple[int, int, int, int], Any]] | None = None,
        chunk_size: int = 50000,
        redraw: bool = True,
    ) -> None:
        """Add points with uncertainty ellipses to the layer.

        Args:
            coords: List of (lat, lon) tuples for each point.
            sma_m: List of semi-major axis values in meters.
            smi_m: List of semi-minor axis values in meters.
            tilt_deg: List of tilt angles in degrees clockwise from true north.
            ids: Optional list of feature IDs. Auto-generated if not provided.
            colors_rgba: Optional list of colors. Each color can be either:
                - RGBA tuple: (r, g, b, a) with values 0-255
                - QColor object from PySide6.QtGui
            chunk_size: Number of points per chunk to avoid large JSON payloads.
            redraw: Whether to request a redraw after the final chunk is sent.
        """
        if not len(coords) == len(sma_m) == len(smi_m) == len(tilt_deg):
            raise ValueError("coords/sma_m/smi_m/tilt_deg must have the same length")

        n = len(coords)
        if ids is not None and len(ids) != n:
            raise ValueError("ids must have the same length as coords")
        if colors_rgba is not None and len(colors_rgba) != n:
            raise ValueError("colors_rgba must have the same length as coords")
        if n == 0:
            return

        # Chunking avoids huge JSON payloads that can stall the JS thread.
        if chunk_size <= 0:
            chunk_size = n

        for start in range(0, n, chunk_size):
            end = min(n, start + chunk_size)
            # Swap lat,lon (public API) to lon,lat (internal format)
            coords_chunk = _latlon_chunk_to_lonlat_list(coords[start:end])

            msg: dict = {
                "type": "fast_geopoints.add_points",
                "layer_id": self.id,
                "coords": coords_chunk,
                "sma_m": np.asarray(sma_m[start:end], dtype=float).tolist(),
                "smi_m": np.asarray(smi_m[start:end], dtype=float).tolist(),
                "tilt_deg": np.asarray(tilt_deg[start:end], dtype=float).tolist(),
                "redraw": bool(redraw and end == n),
            }
            if ids is not None:
                msg["ids"] = ids[start:end]
            if colors_rgba is not None:
                msg["colors"] = _pack_rgba_colors(colors_rgba[start:end])
            self._map_widget._send(msg)


    def redraw(self) -> None:
        """Request a redraw after one or more deferred FastGeoPoints updates."""
        self._map_widget._send({"type": "fast_geopoints.redraw", "layer_id": self.id})

    def remove_ids(self, feature_ids: Sequence[str]) -> None:
        """Remove fast geopoints by id (marks deleted in JS)."""
        self._map_widget._send(
            {
                "type": "fast_geopoints.remove_ids",
                "layer_id": self.id,
                "feature_ids": [str(x) for x in feature_ids],
            }
        )

    def set_ellipses_visible(self, visible: bool) -> None:
        """Toggle unselected ellipse drawing while leaving points visible."""
        self._map_widget._send(
            {
                "type": "fast_geopoints.set_ellipses_visible",
                "layer_id": self.id,
                "visible": bool(visible),
            }
        )

    def set_selected_ellipses_visible(self, visible: bool) -> None:
        """Toggle selected ellipse drawing while keeping point selection visible."""
        self._map_widget._send(
            {
                "type": "fast_geopoints.set_selected_ellipses_visible",
                "layer_id": self.id,
                "visible": bool(visible),
            }
        )

    def hide_features(self, feature_ids: Sequence[str]) -> None:
        """Hide features by id (temporarily hide from view; can be unhidden)."""
        fids = [str(x) for x in feature_ids]
        self._map_widget._send(
            {
                "type": "fast_geopoints.hide_ids",
                "layer_id": self.id,
                "feature_ids": fids,
                "ids": fids,
            }
        )

    def show_features(self, feature_ids: Sequence[str]) -> None:
        """Show previously hidden features by id."""
        fids = [str(x) for x in feature_ids]
        self._map_widget._send(
            {
                "type": "fast_geopoints.show_ids",
                "layer_id": self.id,
                "feature_ids": fids,
                "ids": fids,
            }
        )

    def show_all_features(self) -> None:
        """Show all hidden features (reset filter)."""
        self._map_widget._send(
            {
                "type": "fast_geopoints.show_all",
                "layer_id": self.id,
            }
        )

    def set_colors(
        self,
        feature_ids: Sequence[str],
        colors_rgba: list[Union[tuple[int, int, int, int], Any]],
    ) -> None:
        """Update colors for specific features by ID.

        This allows changing colors of selected or any other features.

        Args:
            feature_ids: List of feature IDs to update.
            colors_rgba: List of colors, one per feature ID. Each color can be either:
                - RGBA tuple: (r, g, b, a) with values 0-255
                - QColor object from PySide6.QtGui
        """
        if len(feature_ids) != len(colors_rgba):
            raise ValueError("feature_ids and colors_rgba must have the same length")

        fids = [str(x) for x in feature_ids]
        packed = _pack_rgba_colors(colors_rgba)

        self._map_widget._send(
            {
                "type": "fast_geopoints.set_colors",
                "layer_id": self.id,
                "feature_ids": fids,
                "colors": packed,
            }
        )
