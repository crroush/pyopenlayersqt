#!/usr/bin/env python3
"""Dynamic DTED terrain overlay with debounced re-render on zoom/pan.

Usage:
    python examples/17_dted_terrain_overlay.py --dted-root ~/dted
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import sys
import time
from typing import Dict, Optional, Tuple

import numpy as np
from PySide6 import QtCore, QtWidgets

from pyopenlayersqt import DTEDStore, OLMapWidget, RasterStyle

FT_TO_M = 0.3048


@dataclass(frozen=True)
class RenderResult:
    request_id: int
    key: Tuple[float, ...]
    png: bytes
    bounds: list[tuple[float, float]]
    elapsed_ms: float


class DTEDTerrainRenderer(QtWidgets.QMainWindow):
    renderReady = QtCore.Signal(object)

    def __init__(self, args: argparse.Namespace):
        super().__init__()
        self.setWindowTitle("DTED Terrain (Dynamic + Debounced)")
        self.resize(1280, 900)

        self._terrain_enabled = not bool(args.disable_terrain)
        self._dpr_scale = float(args.pixel_ratio_scale)
        self._max_render_px = int(args.max_render_px)
        self._max_tiles = int(args.max_tiles)
        self._current_request_id = 0
        self._latest_applied_id = 0
        self._last_requested_key: Optional[Tuple[float, ...]] = None
        self._cmap = args.cmap
        self._color_unit = args.color_unit
        self._color_range: Optional[Tuple[float, float]] = None
        if args.color_min is not None and args.color_max is not None:
            lo = float(args.color_min)
            hi = float(args.color_max)
            if self._color_unit == "feet":
                lo *= FT_TO_M
                hi *= FT_TO_M
            self._color_range = (lo, hi)

        self._render_cache_size = max(1, int(args.render_cache_size))
        self._render_cache: "OrderedDict[Tuple[float, ...], tuple[bytes, list[tuple[float, float]]]]" = OrderedDict()

        self._store = DTEDStore(args.dted_root, cache_size=int(args.tile_cache_size))
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._pending_future: Optional[Future] = None

        self.map_widget = OLMapWidget(center=(args.center_lat, args.center_lon), zoom=args.zoom)
        self.raster_layer = None

        controls = self._build_controls()

        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(controls)
        layout.addWidget(self.map_widget, stretch=1)
        self.setCentralWidget(container)

        self.map_widget.ready.connect(self._on_map_ready)
        self.renderReady.connect(self._apply_render_result)

    def closeEvent(self, event):  # pylint: disable=invalid-name
        self._executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)

    def _build_controls(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(panel)

        self.enable_cb = QtWidgets.QCheckBox("Enable terrain")
        self.enable_cb.setChecked(self._terrain_enabled)
        self.enable_cb.toggled.connect(self._on_toggle_terrain)
        layout.addWidget(self.enable_cb)

        layout.addWidget(QtWidgets.QLabel("Opacity"))
        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(80)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        layout.addWidget(self.opacity_slider, stretch=1)

        self.status_label = QtWidgets.QLabel("Waiting for map extent...")
        self.status_label.setMinimumWidth(500)
        layout.addWidget(self.status_label, stretch=2)

        return panel

    def _on_map_ready(self):
        # Debounced callback from JS-side view changes.
        self._watch_handle = self.map_widget.watch_view_extent(self._on_view_extent, debounce_ms=180)

    def _extent_key(self, ext: Dict[str, float]) -> Tuple[float, ...]:
        width_px = max(128, int(float(ext.get("width_px", 1024.0)) * self._dpr_scale))
        height_px = max(128, int(float(ext.get("height_px", 768.0)) * self._dpr_scale))
        width_px = min(width_px, self._max_render_px)
        height_px = min(height_px, self._max_render_px)

        # Quantize key enough to avoid unnecessary re-renders while panning tiny amounts.
        return (
            float(ext["lat_min"]),
            float(ext["lon_min"]),
            float(ext["lat_max"]),
            float(ext["lon_max"]),
            width_px,
            height_px,
            round(float(ext.get("resolution", 0.0)), 3),
        )

    def _on_view_extent(self, extent: Dict[str, float]):
        if not self._terrain_enabled:
            return

        try:
            key = self._extent_key(extent)
        except KeyError:
            return

        if key == self._last_requested_key:
            return
        self._last_requested_key = key

        tile_est = max(1, int(np.ceil(abs(key[2] - key[0])))) * max(1, int(np.ceil(abs(key[3] - key[1]))))
        if tile_est > self._max_tiles:
            self.status_label.setText(
                f"Zoom in to render terrain (estimated {tile_est} DTED tiles > limit {self._max_tiles})"
            )
            return

        cached = self._render_cache.get(key)
        if cached is not None:
            self._render_cache.move_to_end(key)
            png, bounds = cached
            self._ensure_layer_and_set(png, bounds)
            self.status_label.setText(f"Terrain cache hit | {key[4]}x{key[5]} px | bounds={key[0]:.5f},{key[1]:.5f}→{key[2]:.5f},{key[3]:.5f}")
            return

        self._current_request_id += 1
        request_id = self._current_request_id

        self.status_label.setText(
            f"Rendering terrain... req={request_id} | {key[4]}x{key[5]} px | res≈{key[6]} m/px"
        )

        if self._pending_future and not self._pending_future.done():
            self._pending_future.cancel()

        self._pending_future = self._executor.submit(self._render_for_extent, request_id, key)
        self._pending_future.add_done_callback(self._on_render_done)

    def _render_for_extent(self, request_id: int, key: Tuple[float, ...]) -> RenderResult:
        t0 = time.perf_counter()
        lat_min, lon_min, lat_max, lon_max, width_px, height_px, _res = key

        polygon = [
            (lat_min, lon_min),
            (lat_min, lon_max),
            (lat_max, lon_max),
            (lat_max, lon_min),
        ]

        terrain = self._store.sample_polygon_grid(
            polygon_latlon=polygon,
            width=int(width_px),
            height=int(height_px),
            nodata_value=np.nan,
        )
        if self._color_range is None:
            finite = np.isfinite(terrain.grid_m)
            if finite.any():
                self._color_range = (
                    float(np.nanmin(terrain.grid_m)),
                    float(np.nanmax(terrain.grid_m)),
                )

        color_min, color_max = (self._color_range if self._color_range is not None else (None, None))
        png = self._store.terrain_to_heatmap_png(
            terrain,
            cmap=self._cmap,
            alpha=1.0,
            vmin=color_min,
            vmax=color_max,
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        bounds = [terrain.bounds[0], terrain.bounds[1]]
        return RenderResult(request_id=request_id, key=key, png=png, bounds=bounds, elapsed_ms=elapsed_ms)

    def _on_render_done(self, future: Future):
        if future.cancelled():
            return
        exc = future.exception()
        if exc is not None:
            QtCore.QTimer.singleShot(0, lambda: self.status_label.setText(f"Render error: {exc}"))
            return

        result = future.result()
        self.renderReady.emit(result)

    @QtCore.Slot(object)
    def _apply_render_result(self, result: RenderResult):
        # Never apply stale renders; only the newest requested frame can paint.
        if result.request_id != self._current_request_id:
            return
        self._latest_applied_id = result.request_id

        self._render_cache[result.key] = (result.png, result.bounds)
        self._render_cache.move_to_end(result.key)
        while len(self._render_cache) > self._render_cache_size:
            self._render_cache.popitem(last=False)

        self._ensure_layer_and_set(result.png, result.bounds)
        self.status_label.setText(
            f"Rendered req={result.request_id} in {result.elapsed_ms:.1f} ms | {result.key[4]}x{result.key[5]} px"
        )

    def _ensure_layer_and_set(self, png: bytes, bounds: list[tuple[float, float]]):
        if self.raster_layer is None:
            self.raster_layer = self.map_widget.add_raster_image(
                png,
                bounds=bounds,
                style=RasterStyle(opacity=self.opacity_slider.value() / 100.0),
                name="terrain",
            )
        else:
            self.raster_layer.set_image(png, bounds=bounds)

    def _on_toggle_terrain(self, checked: bool):
        self._terrain_enabled = bool(checked)
        if not checked and self.raster_layer is not None:
            self.raster_layer.remove()
            self.raster_layer = None
            self.status_label.setText("Terrain disabled")
        elif checked:
            self.status_label.setText("Terrain enabled; waiting for next debounced view update...")
            self.map_widget.get_view_extent(self._on_view_extent)

    def _on_opacity_changed(self, value: int):
        if self.raster_layer is not None:
            self.raster_layer.set_opacity(value / 100.0)



def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dynamic DTED terrain overlay demo")
    parser.add_argument("--dted-root", required=True, help="Path to DTED root directory (required)")
    parser.add_argument("--disable-terrain", action="store_true", help="Start with terrain overlay disabled")
    parser.add_argument("--center-lat", type=float, default=29.0)
    parser.add_argument("--center-lon", type=float, default=-106.0)
    parser.add_argument("--zoom", type=int, default=7)
    parser.add_argument("--tile-cache-size", type=int, default=24, help="DTED tile LRU cache size")
    parser.add_argument("--render-cache-size", type=int, default=8, help="Rendered view LRU cache size")
    parser.add_argument("--max-render-px", type=int, default=1024, help="Max render width/height in px")
    parser.add_argument("--max-tiles", type=int, default=400, help="Skip rendering when extent spans too many DTED tiles")
    parser.add_argument("--cmap", default="viridis", help="Matplotlib colormap name (default: viridis)")
    parser.add_argument("--color-min", type=float, default=0.0, help="Fixed minimum elevation for color scaling")
    parser.add_argument("--color-max", type=float, default=15000.0, help="Fixed maximum elevation for color scaling")
    parser.add_argument("--color-unit", choices=["feet", "meters"], default="feet", help="Units for --color-min/--color-max (default: feet)")
    parser.add_argument(
        "--pixel-ratio-scale",
        type=float,
        default=1.0,
        help="Multiplier applied to viewport pixels when sampling DTED",
    )
    return parser


if __name__ == "__main__":
    args = _build_arg_parser().parse_args()
    if args.color_min is not None and args.color_max <= args.color_min:
        raise SystemExit("--color-max must be greater than --color-min.")

    app = QtWidgets.QApplication(sys.argv)
    win = DTEDTerrainRenderer(args)
    win.show()
    sys.exit(app.exec())
