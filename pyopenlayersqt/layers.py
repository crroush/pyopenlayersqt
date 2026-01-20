from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .models import (
    CircleStyle,
    EllipseStyle,
    LonLat,
    PointStyle,
    PolygonStyle,
    RasterStyle,
    WMSOptions,
)


class BaseLayer:
    def __init__(self, widget: Any, layer_id: str, name: str = ""):
        self._w = widget
        self.id = layer_id
        self.name = name or layer_id

    def remove(self) -> None:
        self._w._send({"type": "layer.remove", "layer_id": self.id})

    def set_opacity(self, opacity: float) -> None:
        self._w._send(
            {"type": "layer.opacity", "layer_id": self.id, "opacity": float(opacity)}
        )


class VectorLayer(BaseLayer):
    """
    A layer that can hold points/polygons/lines/circles/ellipses as vector features.
    """

    def clear(self) -> None:
        self._w._send({"type": "vector.clear", "layer_id": self.id})

    def remove_features(self, feature_ids: Sequence[str]) -> None:
        """Remove vector features by id."""
        self._w.send(
            {
                "type": "vector.remove_features",
                "layer_id": self.id,
                "feature_ids": [str(x) for x in feature_ids],
            }
        )

    def add_points(
        self,
        coords: Sequence[LonLat],
        ids: Optional[Sequence[str]] = None,
        style: Optional[PointStyle] = None,
        properties: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> None:
        style = style or PointStyle()
        ids = list(ids) if ids is not None else [f"pt{i}" for i in range(len(coords))]
        props = (
            list(properties)
            if properties is not None
            else [{} for _ in range(len(coords))]
        )
        self._w._send(
            {
                "type": "vector.add_points",
                "layer_id": self.id,
                "coords": [[float(lon), float(lat)] for (lon, lat) in coords],
                "ids": list(ids),
                "style": style.to_js(),
                "properties": props,
            }
        )

    def add_polygon(
        self,
        ring: Sequence[LonLat],
        feature_id: str = "poly0",
        style: Optional[PolygonStyle] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        style = style or PolygonStyle()
        self._w._send(
            {
                "type": "vector.add_polygon",
                "layer_id": self.id,
                "ring": [[float(lon), float(lat)] for (lon, lat) in ring],
                "id": feature_id,
                "style": style.to_js(),
                "properties": properties or {},
            }
        )

    def add_line(
        self,
        coords: Sequence[LonLat],
        feature_id: str = "line0",
        style: Optional[PolygonStyle] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add a polyline (non-closed) feature to this vector layer.

        coords: sequence of (lon, lat) tuples describing the line vertices in order.
        feature_id: the feature id to assign.
        style: a PolygonStyle (uses stroke_* attributes) or None for defaults.
        properties: optional dict of properties to attach to the feature.
        """
        style = style or PolygonStyle()
        self._w._send(
            {
                "type": "vector.add_line",
                "layer_id": self.id,
                "coords": [[float(lon), float(lat)] for (lon, lat) in coords],
                "id": feature_id,
                "style": style.to_js(),
                "properties": properties or {},
            }
        )

    def add_circle(
        self,
        center: LonLat,
        radius_m: float,
        feature_id: str = "circle0",
        style: Optional[CircleStyle] = None,
        properties: Optional[Dict[str, Any]] = None,
        segments: int = 72,
    ) -> None:
        style = style or CircleStyle()
        self._w._send(
            {
                "type": "vector.add_circle",
                "layer_id": self.id,
                "center": [float(center[0]), float(center[1])],
                "radius_m": float(radius_m),
                "id": feature_id,
                "style": style.to_js(),
                "properties": properties or {},
                "segments": int(segments),
            }
        )

    def add_ellipse(
        self,
        center: LonLat,
        sma_m: float,
        smi_m: float,
        tilt_deg: float,
        feature_id: str = "ell0",
        style: Optional[EllipseStyle] = None,
        properties: Optional[Dict[str, Any]] = None,
        segments: int = 96,
    ) -> None:
        style = style or EllipseStyle()
        self._w._send(
            {
                "type": "vector.add_ellipse",
                "layer_id": self.id,
                "center": [float(center[0]), float(center[1])],
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
        self._w._send(
            {"type": "wms.set_params", "layer_id": self.id, "params": dict(params)}
        )


class RasterLayer(BaseLayer):
    """
    Image overlay layer (PNG served by the widget HTTP server).
    """

    def __init__(
        self,
        widget: Any,
        layer_id: str,
        url: str,
        bounds: List[LonLat],
        style: RasterStyle,
        name: str = "",
    ):
        super().__init__(widget, layer_id, name=name or layer_id)
        self.url = url
        self.bounds = bounds  # [minLonLat, maxLonLat] or 4-corner ring (we use extent)
        self.style = style

    def set_image(self, url: str, bounds: List[LonLat]) -> None:
        self.url = url
        self.bounds = bounds
        self._w._send(
            {
                "type": "raster.set_image",
                "layer_id": self.id,
                "url": url,
                "bounds": [[float(lon), float(lat)] for lon, lat in bounds],
            }
        )

    def set_style(self, style: RasterStyle) -> None:
        self.style = style
        self.set_opacity(style.opacity)


class FastPointsLayer:
    """High-volume point layer (IDs-only selection).

    Backed by a JS-side spatial grid index + canvas renderer.
    No per-point ol.Feature objects.
    """

    def __init__(
        self, map_widget: "OLMapWidget", layer_id: str, name: str = ""
    ) -> None:
        self._mapw = map_widget
        self.id = layer_id
        self.name = name or layer_id

    def add_points(
        self,
        coords: list[tuple[float, float]],
        ids: list[str] | None = None,
        colors_rgba: list[tuple[int, int, int, int]] | None = None,
    ) -> None:
        msg: dict = {
            "type": "fast_points.add_points",
            "layer_id": self.id,
            "coords": coords,
        }
        if ids is not None:
            msg["ids"] = ids
        if colors_rgba is not None:
            packed: list[int] = []
            for r, g, b, a in colors_rgba:
                packed.append(
                    ((r & 255) << 24) | ((g & 255) << 16) | ((b & 255) << 8) | (a & 255)
                )
            msg["colors"] = packed
        self._mapw._send(msg)

    def clear(self) -> None:
        self._mapw._send({"type": "fast_points.clear", "layer_id": self.id})

    def set_opacity(self, opacity: float) -> None:
        self._mapw._send(
            {
                "type": "fast_points.set_opacity",
                "layer_id": self.id,
                "opacity": float(opacity),
            }
        )

    def set_visible(self, visible: bool) -> None:
        self._mapw._send(
            {
                "type": "fast_points.set_visible",
                "layer_id": self.id,
                "visible": bool(visible),
            }
        )

    def set_selectable(self, selectable: bool) -> None:
        self._mapw._send(
            {
                "type": "fast_points.set_selectable",
                "layer_id": self.id,
                "selectable": bool(selectable),
            }
        )

    def remove_points(self, feature_ids: Sequence[str]) -> None:
        """Remove fast points by id (marks deleted in JS)."""
        # Send both 'feature_ids' and 'ids' for compatibility with any older/newer JS.
        fids = [str(x) for x in feature_ids]
        self._mapw._send(
            {
                "type": "fast_points.remove_ids",
                "layer_id": self.id,
                "feature_ids": fids,
                "ids": fids,
            }
        )



class FastGeoPointsLayer:
    """High-volume geolocation layer: points with attached uncertainty ellipses.

    Each point has:
      - lon/lat
      - sma_m, smi_m (meters)
      - tilt_deg clockwise from true north

    Rendering is canvas-based with a grid index (like FastPointsLayer).
    Ellipses can be toggled on/off independently of points.
    """

    def __init__(self, map_widget: "OLMapWidget", layer_id: str, name: str = "") -> None:
        self._mapw = map_widget
        self.id = layer_id
        self.name = name or layer_id

    def add_points_with_ellipses(
        self,
        coords: list[tuple[float, float]],
        sma_m: list[float],
        smi_m: list[float],
        tilt_deg: list[float],
        ids: list[str] | None = None,
        colors_rgba: list[tuple[int, int, int, int]] | None = None,
        chunk_size: int = 50000,
    ) -> None:
        if not (len(coords) == len(sma_m) == len(smi_m) == len(tilt_deg)):
            raise ValueError("coords/sma_m/smi_m/tilt_deg must have the same length")

        n = len(coords)
        if n == 0:
            return

        # Chunking avoids huge JSON payloads that can stall the JS thread.
        if chunk_size <= 0:
            chunk_size = n

        for start in range(0, n, chunk_size):
            end = min(n, start + chunk_size)
            msg: dict = {
                "type": "fast_geopoints.add_points",
                "layer_id": self.id,
                "coords": coords[start:end],
                "sma_m": [float(x) for x in sma_m[start:end]],
                "smi_m": [float(x) for x in smi_m[start:end]],
                "tilt_deg": [float(x) for x in tilt_deg[start:end]],
            }
            if ids is not None:
                msg["ids"] = ids[start:end]
            if colors_rgba is not None:
                packed: list[int] = []
                for r, g, b, a in colors_rgba[start:end]:
                    packed.append(
                        ((r & 255) << 24)
                        | ((g & 255) << 16)
                        | ((b & 255) << 8)
                        | (a & 255)
                    )
                msg["colors"] = packed
            self._mapw._send(msg)

    def clear(self) -> None:
        self._mapw._send({"type": "fast_geopoints.clear", "layer_id": self.id})

    def remove_ids(self, feature_ids: Sequence[str]) -> None:
        self._mapw._send(
            {
                "type": "fast_geopoints.remove_ids",
                "layer_id": self.id,
                "feature_ids": [str(x) for x in feature_ids],
            }
        )

    def set_opacity(self, opacity: float) -> None:
        self._mapw._send(
            {
                "type": "fast_geopoints.set_opacity",
                "layer_id": self.id,
                "opacity": float(opacity),
            }
        )

    def set_visible(self, visible: bool) -> None:
        self._mapw._send(
            {
                "type": "fast_geopoints.set_visible",
                "layer_id": self.id,
                "visible": bool(visible),
            }
        )

    def set_selectable(self, selectable: bool) -> None:
        self._mapw._send(
            {
                "type": "fast_geopoints.set_selectable",
                "layer_id": self.id,
                "selectable": bool(selectable),
            }
        )

    def set_ellipses_visible(self, visible: bool) -> None:
        """Toggle ellipse drawing while leaving points visible."""
        self._mapw._send(
            {
                "type": "fast_geopoints.set_ellipses_visible",
                "layer_id": self.id,
                "visible": bool(visible),
            }
        )
