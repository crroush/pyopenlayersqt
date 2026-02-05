from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Union

from .models import (
    CircleStyle,
    EllipseStyle,
    LatLon,
    PointStyle,
    PolygonStyle,
    RasterStyle,
    WMSOptions,
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


def _normalize_color(color: Union[tuple[int, int, int, int], str, Any]) -> tuple[int, int, int, int]:
    """Normalize a color to RGBA tuple format.
    
    Accepts:
    - RGBA tuple: (r, g, b, a) with values 0-255
    - QColor object from PySide6.QtGui
    - Color name string (e.g., 'Green', 'Red', 'blue')
    
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
        try:
            from PySide6.QtGui import QColor
            qcolor = QColor(color)
            if qcolor.isValid():
                return (qcolor.red(), qcolor.green(), qcolor.blue(), qcolor.alpha())
        except ImportError:
            pass
        raise ValueError(f"Invalid color name: {color}")
    
    raise TypeError(
        f"Color must be an RGBA tuple (r, g, b, a), a QColor object, "
        f"or a color name string, got {type(color)}"
    )


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
            {"type": msg_type, "layer_id": self.id, "opacity": float(opacity)}
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
        styles: Sequence[PointStyle | PolygonStyle | CircleStyle | EllipseStyle],
    ) -> None:
        """Update styles for specific features by ID.

        This allows changing colors and other style properties of selected or any features.

        Args:
            feature_ids: List of feature IDs to update.
            styles: List of style objects, one per feature ID. Use the appropriate
                    style type for each feature (PointStyle, PolygonStyle, etc.).
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
        style: Optional[PointStyle] = None,
        properties: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> None:
        """Add point features to the layer.

        Args:
            coords: Sequence of (lat, lon) tuples for each point.
            ids: Optional sequence of feature IDs. Auto-generated if not provided.
            style: Point styling. Uses default if not provided.
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

    def set_image(self, url: str, bounds: List[LatLon]) -> None:
        """Update the raster image.

        Args:
            url: URL or path to the image.
            bounds: Two (lat, lon) tuples defining SW and NE corners.
        """
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
    ) -> None:
        """Add points to the layer.

        Args:
            coords: List of (lat, lon) tuples for each point.
            ids: Optional list of feature IDs. Auto-generated if not provided.
            colors_rgba: Optional list of colors. Each color can be either:
                - RGBA tuple: (r, g, b, a) with values 0-255
                - QColor object from PySide6.QtGui
        """
        # Swap lat,lon (public API) to lon,lat (internal format)
        coords_internal = [[lon, lat] for lat, lon in coords]

        msg: dict = {
            "type": "fast_points.add_points",
            "layer_id": self.id,
            "coords": coords_internal,
        }
        if ids is not None:
            msg["ids"] = ids
        if colors_rgba is not None:
            msg["colors"] = _pack_rgba_colors(colors_rgba)
        self._map_widget._send(msg)

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
        """
        if not len(coords) == len(sma_m) == len(smi_m) == len(tilt_deg):
            raise ValueError("coords/sma_m/smi_m/tilt_deg must have the same length")

        n = len(coords)
        if n == 0:
            return

        # Chunking avoids huge JSON payloads that can stall the JS thread.
        if chunk_size <= 0:
            chunk_size = n

        for start in range(0, n, chunk_size):
            end = min(n, start + chunk_size)
            # Swap lat,lon (public API) to lon,lat (internal format)
            coords_chunk = [[lon, lat] for lat, lon in coords[start:end]]

            msg: dict = {
                "type": "fast_geopoints.add_points",
                "layer_id": self.id,
                "coords": coords_chunk,
                "sma_m": [float(x) for x in sma_m[start:end]],
                "smi_m": [float(x) for x in smi_m[start:end]],
                "tilt_deg": [float(x) for x in tilt_deg[start:end]],
            }
            if ids is not None:
                msg["ids"] = ids[start:end]
            if colors_rgba is not None:
                msg["colors"] = _pack_rgba_colors(colors_rgba[start:end])
            self._map_widget._send(msg)

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
        """Toggle ellipse drawing while leaving points visible."""
        self._map_widget._send(
            {
                "type": "fast_geopoints.set_ellipses_visible",
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
