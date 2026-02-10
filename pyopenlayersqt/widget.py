from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from dataclasses import asdict, is_dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple, Union

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QObject, Signal, Slot, QUrl, QStandardPaths, QTimer
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

from .layers import (
    RasterLayer,
    VectorLayer,
    WMSLayer,
    FastPointsLayer,
    FastGeoPointsLayer,
)
from .models import (
    FeatureSelection,
    RasterStyle,
    WMSOptions,
    FastPointsStyle,
    FastGeoPointsStyle,
)

PKG_DIR = Path(__file__).resolve().parent


def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    return str(obj)


def _default_overlays_dir(app_name: str = "pyopenlayersqt") -> Path:
    """
    Writable per-user directory.
    This is used for heatmap overlays
    """
    base = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
    if not base:
        base = str(Path.home() / ".cache" / app_name)
    p = Path(base) / "overlays"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _is_http_url(s: str) -> bool:
    s = s.strip()
    return s.startswith("http://") or s.startswith("https://")


class _Bridge(QObject):
    eventReceived = Signal(str, str)

    @Slot(str, str)
    def emitEvent(self, event_type: str, payload_json: str) -> None:
        self.eventReceived.emit(event_type, payload_json)


class _StaticServer:
    """
    Serves:
      - /resources/* and /vendor/* from installed package directory
      - /_overlays/* from a writable per-user directory
    """

    def __init__(
        self, pkg_dir: Path, overlays_dir: Path, host: str = "127.0.0.1", port: int = 0
    ):
        self.pkg_dir = pkg_dir
        self.overlays_dir = overlays_dir
        self.host = host
        self.port = port
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> Tuple[str, int]:
        pkg_dir = self.pkg_dir
        overlays_dir = self.overlays_dir

        class Handler(SimpleHTTPRequestHandler):
            def translate_path(self, path: str) -> str:
                path = path.split("?", 1)[0].split("#", 1)[0]
                rel = path.lstrip("/")

                # overlays served from user-writable folder
                if rel.startswith("_overlays/"):
                    return str(overlays_dir / rel[len("_overlays/") :])

                # everything else from package dir
                return str(pkg_dir / rel)

            def log_message(self, _fmt: str, *args: Any) -> None:
                return  # quiet

        self._httpd = ThreadingHTTPServer((self.host, int(self.port)), Handler)
        self.port = int(self._httpd.server_address[1])

        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

        return self.host, self.port

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
            except Exception:
                pass
            try:
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None


class OLMapWidget(QWebEngineView):
    """
    QWebEngineView embedding OpenLayers.

    Python -> JS: window.pyolqt_send(<json-string>)
    JS -> Python: qtBridge.emitEvent(type, payload_json)
    """

    # Default initial view settings
    DEFAULT_CENTER = (0.0, 0.0)  # (lat, lon) - centered at equator and prime meridian
    DEFAULT_ZOOM = 2

    selectionChanged = Signal(object)  # FeatureSelection
    viewExtentReceived = Signal(object)
    viewExtentChanged = Signal(object)
    jsEvent = Signal(str, str)
    ready = Signal()
    perfReceived = Signal(object)

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        center: Optional[Tuple[float, float]] = None,
        zoom: Optional[int] = None,
        show_coordinates: bool = True,
    ):
        """Initialize the map widget.

        Args:
            parent: Parent widget
            center: Initial map center as (lat, lon) tuple. Defaults to (0.0, 0.0).
            zoom: Initial zoom level. Defaults to 2.
            show_coordinates: If True, displays mouse lat/lon coordinates in the
                lower right corner. Defaults to True.
        """
        super().__init__(parent)

        # Store initial view settings (public API is lat,lon)
        self._initial_center = center if center is not None else self.DEFAULT_CENTER
        self._initial_zoom = zoom if zoom is not None else self.DEFAULT_ZOOM
        self._show_coordinates = show_coordinates
        self._perf_logging_enabled = (
            os.environ.get("PYOPENLAYERSQT_BENCH", "") == "1"
            or os.environ.get("PYOPENLAYERSQT_PERF", "") == "1"
        )

        # writable overlays
        self._overlays_dir = _default_overlays_dir()

        # static server (wheel-safe)
        self._server = _StaticServer(
            PKG_DIR, overlays_dir=self._overlays_dir, host="127.0.0.1", port=0
        )
        host, port = self._server.start()
        self._base_url = f"http://{host}:{port}"

        # JS->Py bridge
        self._bridge = _Bridge()
        self._bridge.eventReceived.connect(self._on_js_event)

        self._channel = QWebChannel(self.page())
        self._channel.registerObject("qtBridge", self._bridge)
        self.page().setWebChannel(self._channel)

        # layer ids
        self._layer_seq = 0

        # queue until JS is ready (prevents "pyolqt_send is not a function")
        self._js_ready = False
        self._pending: list[Dict[str, Any]] = []

        # load
        self.loadFinished.connect(self._on_load_finished)
        self.setUrl(QUrl(f"{self._base_url}/resources/map.html"))

    # ---------- lifecycle ----------

    def closeEvent(self, ev: QtCore.QEvent) -> None:  # type: ignore[override]
        try:
            self._server.stop()
        except Exception:
            pass
        super().closeEvent(ev)

    # ---------- internal plumbing ----------

    def _next_id(self, prefix: str) -> str:
        self._layer_seq += 1
        return f"{prefix}{self._layer_seq}"

    def _send_now(self, msg: Dict[str, Any]) -> None:
        payload = json.dumps(_to_jsonable(msg), separators=(",", ":"))
        js = f"window.pyolqt_send({json.dumps(payload)});"
        self.page().runJavaScript(js)

    def _send(self, msg: Dict[str, Any]) -> None:
        if not self._js_ready:
            self._pending.append(msg)
            return
        self._send_now(msg)

    def send(self, msg: dict) -> None:
        """Public wrapper around the JS bridge send.

        Args:
          msg: JSON-serializable command dict for the JS bridge.
        """
        self._send(msg)

    def set_vector_selection(self, layer_id: str, feature_ids: list[str]) -> None:
        """Set selection for a vector layer."""
        self.send(
            {"type": "select.set", "layer_id": layer_id, "feature_ids": feature_ids}
        )

    def set_fast_points_selection(self, layer_id: str, feature_ids: list[str]) -> None:
        """Set selection for a fast-points layer."""
        self.send(
            {
                "type": "fast_points.select.set",
                "layer_id": layer_id,
                "feature_ids": feature_ids,
            }
        )

    def set_fast_geopoints_selection(
        self, layer_id: str, feature_ids: list[str]
    ) -> None:
        """Set selection for a fast-geo-points layer."""
        self.send(
            {
                "type": "fast_geopoints.select.set",
                "layer_id": layer_id,
                "feature_ids": feature_ids,
            }
        )

    def set_base_opacity(self, opacity: float) -> None:
        """Set opacity of the base OSM layer (0..1)."""
        self.send({"type": "base.set_opacity", "opacity": float(opacity)})

    def _flush_pending(self) -> None:
        if not self._pending:
            return
        pending = self._pending
        self._pending = []
        for m in pending:
            self._send_now(m)

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            return

        def poll():
            if self._js_ready:
                return
            self.page().runJavaScript(
                "typeof window.pyolqt_send === 'function';", self._on_pyolqt_send_check
            )

        # ol_bridge boot is async; poll a few times
        for ms in (50, 150, 350, 700, 1200):
            QTimer.singleShot(ms, poll)

    def _on_pyolqt_send_check(self, exists: Any) -> None:
        if self._js_ready:
            return
        if exists is True:
            self._js_ready = True
            self._flush_pending()

    def _ensure_overlay_url(self, image: Union[str, bytes, bytearray]) -> str:
        """
        Accepts:
          - http(s) url => returned as-is
          - '/_overlays/..' or '/vendor/..' => returned as-is
          - filesystem path => copied into overlays dir and returned as
            '/_overlays/<uuid>.<ext>?ts=...'
          - PNG bytes => written into overlays dir and returned similarly
        """
        ts = int(time.time() * 1000)

        if isinstance(image, (bytes, bytearray)):
            name = f"{uuid.uuid4().hex}.png"
            dst = self._overlays_dir / name
            dst.write_bytes(bytes(image))
            return f"/_overlays/{name}?ts={ts}"

        s = str(image).strip()
        if not s:
            return s

        if s.startswith("/"):
            # already a server path (e.g. /_overlays/..., /vendor/..., /resources/...)
            return s

        if _is_http_url(s):
            return s

        p = Path(s).expanduser()
        if p.exists() and p.is_file():
            ext = p.suffix or ".png"
            name = f"{uuid.uuid4().hex}{ext}"
            dst = self._overlays_dir / name
            shutil.copy2(p, dst)
            return f"/_overlays/{name}?ts={ts}"

        # fall back: treat as relative URL
        return s

    # ---------- JS -> Python events ----------
    @Slot(str, str)
    def _on_js_event(self, event_type: str, payload_json: str) -> None:
        self.jsEvent.emit(event_type, payload_json)

        if event_type == "ready":
            self._js_ready = True
            # Set initial view if different from defaults
            if (
                self._initial_center != self.DEFAULT_CENTER
                or self._initial_zoom != self.DEFAULT_ZOOM
            ):
                # Swap lat,lon (public API) to lon,lat (internal format)
                lat, lon = self._initial_center
                self._send_now(
                    {
                        "type": "map.set_view",
                        "center": [float(lon), float(lat)],
                        "zoom": int(self._initial_zoom),
                    }
                )
            # Set coordinate display visibility
            self._send_now(
                {"type": "coordinates.set_visible", "visible": self._show_coordinates}
            )
            self._flush_pending()
            self.ready.emit()
            return

        if event_type == "selection":
            try:
                obj = json.loads(payload_json) if payload_json else {}
            except Exception:
                obj = {}
            sel = FeatureSelection(
                layer_id=str(obj.get("layer_id", "")),
                feature_ids=[str(x) for x in obj.get("feature_ids", [])],
                count=int(obj.get("count", len(obj.get("feature_ids", []) or []))),
                raw=obj,
            )
            self.selectionChanged.emit(sel)

            return

        if event_type == "view_extent_changed":
            try:
                obj = json.loads(payload_json) if payload_json else {}
            except Exception:
                obj = {}
            self.viewExtentChanged.emit(obj)
            return

        if event_type == "view_extent":
            try:
                obj = json.loads(payload_json) if payload_json else {}
            except Exception:
                obj = {}
            self.viewExtentReceived.emit(obj)
            return

        if event_type == "perf":
            try:
                obj = json.loads(payload_json) if payload_json else {}
            except Exception:
                obj = {"raw": payload_json}
            if self._perf_logging_enabled:
                try:
                    print("PERF:", obj, flush=True)
                except Exception:
                    pass
            self.perfReceived.emit(obj)
            return

    # ---------- public layer API ----------
    def add_fast_points_layer(
        self,
        name: str,
        selectable: bool = False,
        style: FastPointsStyle | None = None,
        cell_size_m: float = 1000.0,
    ) -> FastPointsLayer:
        layer_id = self._next_id("fp")
        if style is None:
            style = FastPointsStyle()
        self._send(
            {
                "type": "fast_points.add_layer",
                "layer_id": layer_id,
                "name": name,
                "selectable": selectable,
                "cell_size_m": float(cell_size_m),
                "style": style.to_js(),
            }
        )
        return FastPointsLayer(self, layer_id, name=name)

    def add_fast_geopoints_layer(
        self,
        name: str,
        selectable: bool = False,
        style: FastGeoPointsStyle | None = None,
        cell_size_m: float = 1000.0,
        show_ellipses: bool = True,
    ) -> FastGeoPointsLayer:
        """Create a fast geo-points layer (points + attached uncertainty ellipses)."""
        layer_id = self._next_id("fgp")
        if style is None:
            style = FastGeoPointsStyle()
        self._send(
            {
                "type": "fast_geopoints.add_layer",
                "layer_id": layer_id,
                "name": name,
                "selectable": selectable,
                "cell_size_m": float(cell_size_m),
                "style": style.to_js(),
                "ellipses_visible": bool(show_ellipses),
            }
        )
        return FastGeoPointsLayer(self, layer_id, name=name)

    def get_view_extent(self, callback):
        """Request the current visible map extent.

        Async: callback(extent_dict) is called exactly once.
        extent_dict contains lon_min, lat_min, lon_max, lat_max, zoom, resolution, width_px, height_px.

        Note: The extent keys use lon/lat naming but values represent the actual
        geographic bounds regardless of coordinate ordering used elsewhere in the API.
        """

        def once(ext):
            try:
                self.viewExtentReceived.disconnect(once)
            except Exception:
                pass
            callback(ext)

        self.viewExtentReceived.connect(once)
        self._send({"type": "map.get_view_extent"})

    def watch_view_extent(self, callback, debounce_ms: int = 150):
        """Subscribe to extent changes (debounced on the JS side).

        Returns a handle with .cancel(). Starting a new watch automatically
        interrupts (cancels) the previous watch (last-watch-wins).
        """
        self._extent_watch_token = getattr(self, "_extent_watch_token", 0) + 1
        token = int(self._extent_watch_token)

        def handler(ext: object):
            try:
                tok = int(ext.get("token", -1))
            except Exception:
                tok = -1
            if tok != token:
                return
            callback(ext)

        self.viewExtentChanged.connect(handler)
        self._send(
            {
                "type": "map.set_extent_watch",
                "enabled": True,
                "token": token,
                "debounce_ms": int(debounce_ms),
            }
        )

        class Handle:
            def cancel(inner_self):
                try:
                    self.viewExtentChanged.disconnect(handler)
                except Exception:
                    pass
                self._send(
                    {"type": "map.set_extent_watch", "enabled": False, "token": token}
                )

        return Handle()

    def add_vector_layer(
        self, name: str = "vector", selectable: bool = True
    ) -> VectorLayer:
        layer_id = self._next_id("v")
        self._send(
            {
                "type": "layer.add_vector",
                "layer_id": layer_id,
                "name": name,
                "selectable": bool(selectable),
            }
        )
        return VectorLayer(self, layer_id, name=name)

    def add_wms(self, opt: WMSOptions, name: str = "wms") -> WMSLayer:
        layer_id = self._next_id("w")
        self._send(
            {
                "type": "layer.add_wms",
                "layer_id": layer_id,
                "name": name,
                "wms": opt.to_js(),
            }
        )
        return WMSLayer(self, layer_id, opt, name=name)

    def add_raster_image(
        self,
        image_url: Union[str, bytes, bytearray],
        bounds: Sequence[Tuple[float, float]],
        style: Optional[RasterStyle] = None,
        name: str = "raster",
    ) -> RasterLayer:
        """Add a raster image overlay to the map.

        Args:
            image_url: Can be an http(s) URL, a filesystem path, a server path
                      ("/_overlays/..."), or raw PNG bytes.
            bounds: Two (lat, lon) tuples defining SW and NE corners.
            style: Raster styling options.
            name: Layer name.

        Returns:
            The created RasterLayer instance.
        """
        layer_id = self._next_id("r")
        style = style or RasterStyle()
        url = self._ensure_overlay_url(image_url)

        # Swap lat,lon (public API) to lon,lat (internal format)
        self._send(
            {
                "type": "layer.add_raster",
                "layer_id": layer_id,
                "name": name,
                "url": url,
                "bounds": [[float(lon), float(lat)] for lat, lon in bounds],
                "style": style.to_js(),
            }
        )
        return RasterLayer(self, layer_id, url, list(bounds), style, name=name)

    def set_measure_mode(self, enabled: bool) -> None:
        """Enable or disable measurement mode.

        When enabled, clicking on the map creates anchor points for distance measurement.
        Each click emits a 'measurement' event via jsEvent signal with segment and
        cumulative distances.
        Press Escape to exit measurement mode.

        Args:
            enabled: True to enable measurement mode, False to disable.
        """
        self._send({"type": "measure.set_mode", "enabled": bool(enabled)})

    def clear_measurements(self) -> None:
        """Clear all measurement points and lines from the map."""
        self._send({"type": "measure.clear"})

    @property
    def base_url(self) -> str:
        return self._base_url
