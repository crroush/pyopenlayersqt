from __future__ import annotations

import time
import io
import json
import os
import threading
from dataclasses import asdict
from .models import PolygonStyle
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from PySide6.QtCore import QObject, Slot, QUrl, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebChannel import QWebChannel

from .layers import VectorLayer, WMSLayer, RasterLayer
from .models import PointStyle, WMSOptions, RasterStyle


# WSL2/QWebEngine stability knobs (safe to set if not already set)
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu --disable-gpu-compositing"
)
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
os.environ.setdefault("QT_OPENGL", "software")


class _DebugPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        # Keep this lightweight; users can override by subclassing widget if desired
        print(f"[JS] {sourceID}:{lineNumber} {message}")


class _Bridge(QObject):
    eventReceived = Signal(str)  # JSON

    @Slot(str)
    def log(self, msg: str):
        print("JS:", msg)

    @Slot(str)
    def emitEvent(self, payload_json: str):
        self.eventReceived.emit(payload_json)


class _StaticServer:
    def __init__(self, root_dir: Path, host: str = "127.0.0.1", port: int = 8000):
        self.root_dir = root_dir
        self.host = host
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None

    def start(self) -> None:
        root_dir = self.root_dir

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(root_dir), **kwargs)

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        t = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        t.start()

    def shutdown(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


def _ensure_dirs(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _idw_grid(
    lon: np.ndarray,
    lat: np.ndarray,
    z: np.ndarray,
    bounds: tuple[float, float, float, float],
    width: int,
    height: int,
    power: float = 2.0,
    neighbors: int = 12,
) -> np.ndarray:
    """
    Simple IDW gridding with k-nearest (naive). OK for a few thousand points and modest rasters.
    bounds = (minlon, minlat, maxlon, maxlat)
    """
    minlon, minlat, maxlon, maxlat = bounds

    xs = np.linspace(minlon, maxlon, width, dtype=np.float64)
    ys = np.linspace(minlat, maxlat, height, dtype=np.float64)
    grid_lon, grid_lat = np.meshgrid(xs, ys)

    # Flatten grid for distance computation
    glon = grid_lon.ravel()
    glat = grid_lat.ravel()

    # distances in "degree space" (fine for local-ish overlays; for larger extents you’d project first)
    # Compute k-nearest by partial sort on squared distances.
    pts = np.stack([lon, lat], axis=1)  # (N,2)
    grid = np.stack([glon, glat], axis=1)  # (M,2)

    # For memory: process in chunks
    M = grid.shape[0]
    out = np.empty(M, dtype=np.float64)

    chunk = 50_000  # tune as needed
    for i in range(0, M, chunk):
        g = grid[i : i + chunk]  # (C,2)
        # squared distances (C,N)
        d2 = (g[:, None, 0] - pts[None, :, 0]) ** 2 + (
            g[:, None, 1] - pts[None, :, 1]
        ) ** 2
        # choose k nearest indices
        k = min(neighbors, d2.shape[1])
        idx = np.argpartition(d2, kth=k - 1, axis=1)[:, :k]  # (C,k)
        d2k = np.take_along_axis(d2, idx, axis=1)  # (C,k)
        zk = z[idx]  # (C,k)

        # avoid div by 0: if exact point match
        eps = 1e-12
        w = 1.0 / (np.power(d2k + eps, power / 2.0))
        num = np.sum(w * zk, axis=1)
        den = np.sum(w, axis=1)
        out[i : i + chunk] = num / den

    return out.reshape((height, width))


def _colorize_to_png(
    grid: np.ndarray,
    vmin: float | None,
    vmax: float | None,
    cmap_name: str = "terrain",
    alpha: float = 0.55,
    mask: np.ndarray | None = None,
) -> bytes:
    """
    Colorize a 2D float grid to RGBA PNG. Uses matplotlib if available; fallback to grayscale.
    """
    g = np.asarray(grid, dtype=np.float64)
    if vmin is None:
        vmin = float(np.nanmin(g))
    if vmax is None:
        vmax = float(np.nanmax(g))
    if vmax == vmin:
        vmax = vmin + 1e-9

    norm = (g - vmin) / (vmax - vmin)
    norm = np.clip(norm, 0.0, 1.0)

    try:
        import matplotlib.cm as cm
        import matplotlib.colors as mcolors
        from PIL import Image  # pillow

        cmap = cm.get_cmap(cmap_name)
        rgba = cmap(norm, bytes=True)  # (H,W,4) uint8
        if mask is not None:
            # mask True=keep; False=transparent
            rgba[..., 3] = np.where(mask, rgba[..., 3], 0).astype(np.uint8)

        rgba = np.array(rgba, copy=True)
        rgba[..., 3] = (rgba[..., 3].astype(np.float32) * float(alpha)).astype(np.uint8)

        img = Image.fromarray(rgba, mode="RGBA")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    except Exception:
        # Fallback: grayscale PNG without pillow/matplotlib
        # Encode as PPM-like? But we need PNG. We'll require pillow if no matplotlib.
        try:
            from PIL import Image  # pillow

            gray = (norm * 255).astype(np.uint8)
            rgba = np.stack(
                [
                    gray,
                    gray,
                    gray,
                    (np.ones_like(gray) * int(255 * alpha)).astype(np.uint8),
                ],
                axis=-1,
            )
            img = Image.fromarray(rgba, mode="RGBA")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:
            raise RuntimeError(
                "Raster colormap requires Pillow (and optionally matplotlib). "
                "Install: pip install pillow matplotlib"
            ) from e


def _mask_from_polygon_lonlat(
    bounds: tuple[float, float, float, float],
    width: int,
    height: int,
    outer: list[tuple[float, float]],
    holes: list[list[tuple[float, float]]] | None = None,
) -> np.ndarray:
    """
    Returns a boolean mask (H,W) where True means "keep" (inside polygon, excluding holes).
    Polygon coordinates are lon/lat.
    """
    from matplotlib.path import Path as MplPath

    minlon, minlat, maxlon, maxlat = bounds

    # pixel centers
    xs = np.linspace(minlon, maxlon, width, dtype=np.float64)
    ys = np.linspace(minlat, maxlat, height, dtype=np.float64)
    grid_lon, grid_lat = np.meshgrid(xs, ys)
    pts = np.column_stack([grid_lon.ravel(), grid_lat.ravel()])

    def _close_ring(ring):
        if len(ring) < 3:
            raise ValueError("clip_polygon must have at least 3 vertices")
        if ring[0] != ring[-1]:
            ring = list(ring) + [ring[0]]
        return ring

    outer_ring = _close_ring(outer)
    outer_path = MplPath(np.asarray(outer_ring, dtype=np.float64))
    keep = outer_path.contains_points(pts).reshape((height, width))

    if holes:
        for hole in holes:
            hole_ring = _close_ring(hole)
            hole_path = MplPath(np.asarray(hole_ring, dtype=np.float64))
            inside_hole = hole_path.contains_points(pts).reshape((height, width))
            keep &= ~inside_hole

    return keep


class OLMapWidget(QWidget):
    """
    QWebEngine + OpenLayers map widget with a command bus.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        port: int = 8000,
    ):
        super().__init__(parent)

        pkg_root = Path(__file__).resolve().parent
        self._static_root = pkg_root  # serves /vendor and /resources
        self._server = _StaticServer(self._static_root, port=port)
        self._server.start()

        self._view = QWebEngineView(self)
        self._page = _DebugPage(self._view)
        self._view.setPage(self._page)

        self._bridge = _Bridge()
        self._bridge.eventReceived.connect(self._on_event)

        # IMPORTANT: keep channel reference
        self._channel = QWebChannel()
        self._channel.registerObject("bridge", self._bridge)
        self._page.setWebChannel(self._channel)

        self._handlers: dict[str, list[Callable[[dict[str, Any]], None]]] = {
            "select": [],
            "error": [],
        }

        self._ready = False
        self._cmd_queue: list[dict[str, Any]] = []

        self._page.loadFinished.connect(self._on_load_finished)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        # load map template
        url = f"{self._server.base_url}/resources/map.html"
        self._view.load(QUrl(url))

        # overlays storage (served from static root)
        self._overlay_dir = self._static_root / "_overlays"
        _ensure_dirs(self._overlay_dir)

    def closeEvent(self, event) -> None:
        try:
            self._server.shutdown()
        finally:
            super().closeEvent(event)

    # ---------- event handling ----------
    def on_select(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._handlers["select"].append(callback)

    def on_error(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._handlers["error"].append(callback)

    def _on_event(self, payload_json: str) -> None:
        try:
            ev = json.loads(payload_json)
        except Exception:
            return
        t = ev.get("type")
        if t in self._handlers:
            for cb in list(self._handlers[t]):
                cb(ev)

    # ---------- command bus ----------
    def _send(self, cmd: dict[str, Any]) -> None:
        if not self._ready:
            self._cmd_queue.append(cmd)
            return
        js = f"window.__ol_bridge.apply({json.dumps(cmd)});"
        self._page.runJavaScript(js)

    def _on_load_finished(self, ok: bool) -> None:
        self._ready = bool(ok)
        if not self._ready:
            print("OLMapWidget: page failed to load")
            return
        # flush queued commands
        for cmd in self._cmd_queue:
            self._send(cmd)
        self._cmd_queue.clear()

    # ---------- public API ----------
    def add_points(
        self,
        name: str,
        data: list[dict[str, Any]],
        *,
        style: Optional[PointStyle] = None,
    ) -> VectorLayer:
        st = style or PointStyle()
        self._send(
            {"op": "add_points", "layer": name, "data": data, "style": asdict(st)}
        )
        return VectorLayer(self, name)

    def clear_layer(self, name: str) -> None:
        self._send({"op": "clear_layer", "layer": name})

    def remove_layer(self, name: str) -> None:
        self._send({"op": "remove_layer", "layer": name})

    def add_wms(self, opt: WMSOptions) -> WMSLayer:
        self._send(
            {
                "op": "add_wms",
                "layer": opt.name,
                "url": opt.url,
                "layers": opt.layers,
                "opacity": opt.opacity,
                "visible": opt.visible,
                "params": opt.params or {},
            }
        )
        return WMSLayer(self, opt.name)

    def set_visible(self, name: str, visible: bool) -> None:
        self._send({"op": "set_visible", "layer": name, "visible": bool(visible)})

    def set_opacity(self, name: str, opacity: float) -> None:
        self._send({"op": "set_opacity", "layer": name, "opacity": float(opacity)})

    def fit_to_extent(self, extent_lonlat: tuple[float, float, float, float]) -> None:
        self._send(
            {"op": "fit_to_extent", "extent_lonlat": list(map(float, extent_lonlat))}
        )

    def set_selected_ids(self, layer: str, ids: list[Any]) -> None:
        self._send({"op": "set_selected_ids", "layer": layer, "ids": ids})

    # ---------- raster / colormap overlay ----------
    def add_colormap_points(
        self,
        name: str,
        points: list[dict[str, Any]],
        *,
        bounds: tuple[float, float, float, float] | str = "auto",
        clip_polygon: list[tuple[float, float]] | None = None,
        clip_holes: list[list[tuple[float, float]]] | None = None,
        resolution: tuple[int, int] = (512, 512),
        method: str = "idw",
        power: float = 2.0,
        neighbors: int = 12,
        cmap: str = "terrain",
        opacity: float = 0.55,
        vmin: float | None = None,
        vmax: float | None = None,
    ) -> RasterLayer:
        """
        points: [{lon,lat,z,...}] or [{...,"lon":..,"lat":..,"z":..}]
        Renders a PNG overlay served from localhost and adds it as ImageStatic.
        """
        lon = np.array([p["lon"] for p in points], dtype=np.float64)
        lat = np.array([p["lat"] for p in points], dtype=np.float64)
        z = np.array([p["z"] for p in points], dtype=np.float64)

        if bounds == "auto":
            minlon, maxlon = float(np.min(lon)), float(np.max(lon))
            minlat, maxlat = float(np.min(lat)), float(np.max(lat))
            # pad slightly so edges aren’t clipped
            pad_lon = (maxlon - minlon) * 0.02 or 0.001
            pad_lat = (maxlat - minlat) * 0.02 or 0.001
            bounds_ll = (
                minlon - pad_lon,
                minlat - pad_lat,
                maxlon + pad_lon,
                maxlat + pad_lat,
            )
        else:
            bounds_ll = tuple(map(float, bounds))  # type: ignore

        w, h = int(resolution[0]), int(resolution[1])

        if method.lower() != "idw":
            raise ValueError("Only method='idw' is implemented in MVP")

        grid = _idw_grid(
            lon, lat, z, bounds_ll, width=w, height=h, power=power, neighbors=neighbors
        )
        # Optional polygon clipping (turn pixels outside polygon transparent)
        mask = None
        if clip_polygon is not None:
            mask = _mask_from_polygon_lonlat(
                bounds_ll, width=w, height=h, outer=clip_polygon, holes=clip_holes
            )

        png = _colorize_to_png(
            grid, vmin=vmin, vmax=vmax, cmap_name=cmap, alpha=opacity, mask=mask
        )

        # write to overlay path
        out_path = self._overlay_dir / f"{name}.png"
        out_path.write_bytes(png)

        # URL served by static server
        url = f"{self._server.base_url}/_overlays/{name}.png?ts={time.time_ns()}"

        self._send(
            {
                "op": "add_image_overlay",
                "layer": name,
                "url": url,
                "extent_lonlat": list(bounds_ll),
                "opacity": float(opacity),
                "visible": True,
            }
        )

        return RasterLayer(self, name, url=url, extent_lonlat=bounds_ll)

    def add_geojson(
        self,
        name: str,
        geojson: dict[str, Any],
        *,
        geom_type: str = "polygon",
        style: Optional[Any] = None,
        replace: bool = True,
    ) -> VectorLayer:
        """
        Add arbitrary GeoJSON FeatureCollection (EPSG:4326) as a vector layer.
        geom_type: "polygon"|"line"|"point" (used for style selection in JS)
        """
        if style is None:
            style_obj = PolygonStyle()
            style_dict = asdict(style_obj)
        else:
            # dataclass style
            style_dict = asdict(style)

        self._send(
            {
                "op": "add_geojson",
                "layer": name,
                "geojson": geojson,
                "geom_type": geom_type,
                "style": style_dict,
                "replace": bool(replace),
            }
        )
        return VectorLayer(self, name)
