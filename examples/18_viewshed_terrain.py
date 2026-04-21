#!/usr/bin/env python3
"""Terrain viewshed example using AWS terrarium tiles.

This example demonstrates:
- Fetching DEM-like terrain tiles from AWS Open Data (terrarium encoding)
- Computing line-of-sight visibility (viewshed) for one or more observers
- Rendering the resulting visibility mask as an in-memory raster overlay
- Coloring each observer's viewshed independently and compositing overlaps
"""

from __future__ import annotations

import io
import math
import threading
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, PointStyle, RasterStyle

TERRARIUM_URL = "https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png"
WEB_MERCATOR_MAX_LAT = 85.05112878
EARTH_RADIUS_M = 6378137.0


@dataclass
class Observer:
    enabled: bool
    lat: float
    lon: float
    eye_alt_m: float
    color: str


def _clamp_lat(lat: float) -> float:
    return max(min(lat, WEB_MERCATOR_MAX_LAT), -WEB_MERCATOR_MAX_LAT)


def _lonlat_to_tile_xy(lon: float, lat: float, zoom: int) -> Tuple[float, float]:
    lat = _clamp_lat(lat)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * n
    return x, y


def _hex_to_rgb(color: str) -> Tuple[int, int, int]:
    c = color.strip().lstrip("#")
    if len(c) != 6:
        return (255, 0, 0)
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


class TerrainDEM:
    _tile_cache: Dict[Tuple[int, int, int], np.ndarray] = {}
    _tile_cache_order: List[Tuple[int, int, int]] = []
    _tile_cache_max = 512

    def __init__(
        self,
        extent: dict,
        zoom: int,
        progress_cb: Optional[Callable[[str, Optional[int]], None]] = None,
    ):
        self.zoom = int(zoom)
        lon_min = float(extent["lon_min"])
        lon_max = float(extent["lon_max"])
        lat_min = float(extent["lat_min"])
        lat_max = float(extent["lat_max"])

        x0f, y1f = _lonlat_to_tile_xy(lon_min, lat_min, self.zoom)
        x1f, y0f = _lonlat_to_tile_xy(lon_max, lat_max, self.zoom)

        self.tx_min = math.floor(min(x0f, x1f))
        self.tx_max = math.floor(max(x0f, x1f))
        self.ty_min = math.floor(min(y0f, y1f))
        self.ty_max = math.floor(max(y0f, y1f))

        w_tiles = self.tx_max - self.tx_min + 1
        h_tiles = self.ty_max - self.ty_min + 1
        self.mosaic = np.zeros((h_tiles * 256, w_tiles * 256), dtype=np.float32)
        total_tiles = w_tiles * h_tiles
        done_tiles = 0

        for ty in range(self.ty_min, self.ty_max + 1):
            for tx in range(self.tx_min, self.tx_max + 1):
                tile = self._fetch_tile(tx, ty)
                oy = (ty - self.ty_min) * 256
                ox = (tx - self.tx_min) * 256
                self.mosaic[oy : oy + 256, ox : ox + 256] = tile
                done_tiles += 1
                if progress_cb:
                    pct = int(done_tiles * 100 / max(1, total_tiles))
                    progress_cb(
                        f"Downloading terrain tiles... {pct}% ({done_tiles}/{total_tiles})",
                        pct,
                    )

    def _fetch_tile(self, tx: int, ty: int) -> np.ndarray:
        key = (self.zoom, tx, ty)
        cached = self._tile_cache.get(key)
        if cached is not None:
            return cached

        url = TERRARIUM_URL.format(z=self.zoom, x=tx, y=ty)
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        arr = np.asarray(img, dtype=np.float32)
        # Terrarium encoding: elevation = (R*256 + G + B/256) - 32768
        decoded = (arr[:, :, 0] * 256.0 + arr[:, :, 1] + (arr[:, :, 2] / 256.0)) - 32768.0

        self._tile_cache[key] = decoded
        self._tile_cache_order.append(key)
        if len(self._tile_cache_order) > self._tile_cache_max:
            old = self._tile_cache_order.pop(0)
            self._tile_cache.pop(old, None)
        return decoded

    def elevation_m(self, lat: float, lon: float) -> float:
        xf, yf = _lonlat_to_tile_xy(lon, lat, self.zoom)
        px = xf * 256.0 - self.tx_min * 256.0
        py = yf * 256.0 - self.ty_min * 256.0

        px = float(np.clip(px, 0, self.mosaic.shape[1] - 1.001))
        py = float(np.clip(py, 0, self.mosaic.shape[0] - 1.001))

        x0 = int(math.floor(px))
        y0 = int(math.floor(py))
        x1 = min(x0 + 1, self.mosaic.shape[1] - 1)
        y1 = min(y0 + 1, self.mosaic.shape[0] - 1)
        tx = px - x0
        ty = py - y0

        z00 = self.mosaic[y0, x0]
        z10 = self.mosaic[y0, x1]
        z01 = self.mosaic[y1, x0]
        z11 = self.mosaic[y1, x1]
        z0 = z00 * (1.0 - tx) + z10 * tx
        z1 = z01 * (1.0 - tx) + z11 * tx
        return float(z0 * (1.0 - ty) + z1 * ty)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _bresenham_line(x0: int, y0: int, x1: int, y1: int):
    x, y = x0, y0
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        yield x, y
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy


def _observer_viewshed_mask(
    elev_grid: np.ndarray,
    obs_x: int,
    obs_y: int,
    obs_h_m: float,
    meters_per_px: float,
    refraction_coeff: float = 0.13,
) -> np.ndarray:
    h, w = elev_grid.shape
    mask = np.zeros((h, w), dtype=bool)
    mask[obs_y, obs_x] = True

    k = float(np.clip(refraction_coeff, 0.0, 0.5))
    r_eff = EARTH_RADIUS_M / max(1e-6, (1.0 - k))

    for ty in range(h):
        for tx in range(w):
            if tx == obs_x and ty == obs_y:
                continue

            line = list(_bresenham_line(obs_x, obs_y, tx, ty))
            if len(line) < 2:
                mask[ty, tx] = True
                continue

            target_h = float(elev_grid[ty, tx])
            total_d_px = math.hypot(tx - obs_x, ty - obs_y)
            total_d_m = total_d_px * meters_per_px
            if total_d_m <= 0.0:
                mask[ty, tx] = True
                continue

            visible = True
            last_idx = len(line) - 1
            for i, (lx, ly) in enumerate(line[1:-1], start=1):
                t = i / last_idx
                d_m = total_d_m * t

                los_h = obs_h_m + (target_h - obs_h_m) * t
                curvature_drop_m = (d_m * d_m) / (2.0 * r_eff)
                terrain_h = float(elev_grid[ly, lx]) - curvature_drop_m
                if terrain_h > los_h:
                    visible = False
                    break

            mask[ty, tx] = visible
    return mask


def _compute_viewshed_rgba(
    dem: TerrainDEM,
    extent: dict,
    observers: List[Observer],
    width_px: int,
    height_px: int,
    render_mode: str = "not_visible",
    progress_cb: Optional[Callable[[str, Optional[int]], None]] = None,
) -> bytes:
    lon_min = float(extent["lon_min"])
    lon_max = float(extent["lon_max"])
    lat_min = float(extent["lat_min"])
    lat_max = float(extent["lat_max"])

    # Slightly inside pixel centers.
    lon_axis = np.linspace(lon_min, lon_max, width_px, dtype=np.float64)
    lat_axis = np.linspace(lat_max, lat_min, height_px, dtype=np.float64)
    lat_mid = (lat_min + lat_max) * 0.5
    lon_mid = (lon_min + lon_max) * 0.5
    width_m = _haversine_m(lat_mid, lon_min, lat_mid, lon_max)
    height_m = _haversine_m(lat_min, lon_mid, lat_max, lon_mid)
    meters_per_px = max(
        width_m / max(1, width_px - 1),
        height_m / max(1, height_px - 1),
    )

    # Build DEM samples once on output grid.
    elev_grid = np.zeros((height_px, width_px), dtype=np.float32)
    for iy, lat in enumerate(lat_axis):
        for ix, lon in enumerate(lon_axis):
            elev_grid[iy, ix] = dem.elevation_m(float(lat), float(lon))
        if progress_cb and (iy % max(1, height_px // 16) == 0 or iy == height_px - 1):
            pct = int((iy + 1) * 100 / max(1, height_px))
            progress_cb(f"Sampling DEM grid... {pct}%", pct)

    r = np.zeros((height_px, width_px), dtype=np.uint16)
    g = np.zeros((height_px, width_px), dtype=np.uint16)
    b = np.zeros((height_px, width_px), dtype=np.uint16)
    a = np.zeros((height_px, width_px), dtype=np.uint16)

    for idx, obs in enumerate(observers, start=1):
        obs_pct = int(idx * 100 / max(1, len(observers)))
        if progress_cb:
            progress_cb(f"Computing viewshed for observer {idx}/{len(observers)}...", obs_pct)
        cr, cg, cb = _hex_to_rgb(obs.color)
        if lon_max == lon_min or lat_max == lat_min:
            continue
        obs_x = int(round((obs.lon - lon_min) / (lon_max - lon_min) * (width_px - 1)))
        obs_y = int(round((lat_max - obs.lat) / (lat_max - lat_min) * (height_px - 1)))
        obs_x = int(np.clip(obs_x, 0, width_px - 1))
        obs_y = int(np.clip(obs_y, 0, height_px - 1))
        obs_h_m = float(elev_grid[obs_y, obs_x] + obs.eye_alt_m)

        vis_mask = _observer_viewshed_mask(
            elev_grid,
            obs_x,
            obs_y,
            obs_h_m,
            meters_per_px=meters_per_px,
            refraction_coeff=0.13,
        )
        hidden_mask = ~vis_mask

        if render_mode == "visible":
            target_mask = vis_mask
            r[target_mask] += cr
            g[target_mask] += cg
            b[target_mask] += cb
            a[target_mask] += 90
        elif render_mode == "both":
            r[vis_mask] += cr
            g[vis_mask] += cg
            b[vis_mask] += cb
            a[vis_mask] += 100

            # Shade hidden regions slightly darker so both are distinguishable.
            a[hidden_mask] += 35
        else:
            # Default: highlight what is NOT visible from the observer(s).
            r[hidden_mask] += cr
            g[hidden_mask] += cg
            b[hidden_mask] += cb
            a[hidden_mask] += 90

    out = np.zeros((height_px, width_px, 4), dtype=np.uint8)
    out[:, :, 0] = np.clip(r, 0, 255).astype(np.uint8)
    out[:, :, 1] = np.clip(g, 0, 255).astype(np.uint8)
    out[:, :, 2] = np.clip(b, 0, 255).astype(np.uint8)
    out[:, :, 3] = np.clip(a, 0, 220).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(out, mode="RGBA").save(buf, format="PNG")
    return buf.getvalue()


class ViewshedWindow(QtWidgets.QMainWindow):
    workerProgress = Signal(str, int)  # message, pct (-1 means keep current)
    workerSuccess = Signal(bytes, object, int, int, float)  # png, bounds, n_obs, z, extent_km
    workerError = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Viewshed (AWS Terrain)")
        self.resize(1380, 860)

        self.map_widget = OLMapWidget(center=(39.5, -106.0), zoom=10)

        self.observers: List[Observer] = []
        self.viewshed_layer = None
        self.observer_layer = self.map_widget.add_vector_layer("observers", selectable=False)
        self._worker_running = False
        self._extent_request_token = 0
        self._extent_pending = False
        self._map_ready = False
        self._last_render_mode = "not_visible"
        self.map_widget.ready.connect(self._on_map_ready)
        self.workerProgress.connect(self._on_worker_progress)
        self.workerSuccess.connect(self._on_worker_success)
        self.workerError.connect(self._on_worker_error)

        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        layout = QtWidgets.QHBoxLayout(root)

        controls = QtWidgets.QVBoxLayout()
        layout.addLayout(controls, 0)
        layout.addWidget(self.map_widget, 1)

        controls.addWidget(QtWidgets.QLabel("Observer input"))
        self.lat_in = QtWidgets.QLineEdit("39.7392")
        self.lon_in = QtWidgets.QLineEdit("-104.9903")
        self.alt_in = QtWidgets.QLineEdit("50")
        self.color_btn = QtWidgets.QPushButton("Choose Color")
        self.current_color = "#ff0000"
        self._set_color_button_style()
        self.color_btn.clicked.connect(self._choose_color)

        form = QtWidgets.QFormLayout()
        form.addRow("Lat", self.lat_in)
        form.addRow("Lon", self.lon_in)
        form.addRow("Eye Alt (m)", self.alt_in)
        form.addRow("Color", self.color_btn)
        controls.addLayout(form)

        add_btn = QtWidgets.QPushButton("Add Observer")
        add_btn.clicked.connect(self._add_observer)
        controls.addWidget(add_btn)

        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Enabled", "Lat", "Lon", "Alt(m)", "Color"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        controls.addWidget(self.table)

        remove_btn = QtWidgets.QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected)
        controls.addWidget(remove_btn)

        self.res_slider = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.res_slider.setRange(64, 256)
        self.res_slider.setValue(64)
        self.res_slider.setTickInterval(32)
        self.res_slider.valueChanged.connect(
            lambda v: self.res_label.setText(f"Raster size: {v} x {v}")
        )
        self.res_label = QtWidgets.QLabel("Raster size: 64 x 64")
        controls.addWidget(self.res_label)
        controls.addWidget(self.res_slider)

        compute_btn = QtWidgets.QPushButton("Compute Viewshed")
        compute_btn.clicked.connect(self._compute_viewshed)
        controls.addWidget(compute_btn)

        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItem("Not visible (default)", "not_visible")
        self.mode_combo.addItem("Visible", "visible")
        self.mode_combo.addItem("Both", "both")
        controls.addWidget(QtWidgets.QLabel("Render mode"))
        controls.addWidget(self.mode_combo)

        clear_btn = QtWidgets.QPushButton("Clear Raster")
        clear_btn.clicked.connect(self._clear_viewshed)
        controls.addWidget(clear_btn)

        self.status = QtWidgets.QLabel("Ready")
        controls.addWidget(self.status)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls.addWidget(self.progress)
        controls.addStretch(1)

        self._seed_default_observers()

    def _on_map_ready(self):
        self._map_ready = True
        if not self._worker_running:
            self.status.setText("Ready")

    def _on_worker_progress(self, message: str, pct: int):
        self.status.setText(message)
        if pct >= 0:
            self.progress.setValue(int(np.clip(pct, 0, 100)))

    def _on_worker_success(
        self,
        png: bytes,
        bounds: object,
        observer_count: int,
        zoom: int,
        extent_range_km: float,
    ):
        if self.viewshed_layer is None:
            self.viewshed_layer = self.map_widget.add_raster_image(
                png, bounds=bounds, style=RasterStyle(opacity=0.75), name="viewshed"
            )
        else:
            self.viewshed_layer.set_image(png, bounds=bounds)
        self.status.setText(
            f"Viewshed complete | observers={observer_count} | z={zoom} | "
            f"extent_diag={extent_range_km:.1f}km | mode={self._last_render_mode}"
        )
        self.progress.setValue(100)
        self._worker_running = False

    def _on_worker_error(self, message: str):
        self.status.setText(f"Viewshed failed: {message}")
        self.progress.setValue(0)
        self._worker_running = False

    def _set_color_button_style(self):
        self.color_btn.setStyleSheet(f"background: {self.current_color};")

    def _choose_color(self):
        c = QtWidgets.QColorDialog.getColor()
        if c.isValid():
            self.current_color = c.name()
            self._set_color_button_style()

    def _seed_default_observers(self):
        defaults = [
            Observer(True, 39.7392, -104.9903, 60.0, "#ff0000"),
            Observer(True, 39.5501, -105.7821, 60.0, "#00ff00"),
            Observer(False, 39.1911, -106.8175, 60.0, "#0000ff"),
        ]
        for obs in defaults:
            self._append_observer(obs)

    def _append_observer(self, obs: Observer):
        self.observers.append(obs)
        row = self.table.rowCount()
        self.table.insertRow(row)

        enabled_item = QtWidgets.QTableWidgetItem()
        enabled_item.setFlags(enabled_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        enabled_item.setCheckState(Qt.CheckState.Checked if obs.enabled else Qt.CheckState.Unchecked)
        self.table.setItem(row, 0, enabled_item)
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"{obs.lat:.6f}"))
        self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{obs.lon:.6f}"))
        self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(f"{obs.eye_alt_m:.1f}"))

        color_item = QtWidgets.QTableWidgetItem(obs.color)
        color_item.setBackground(QColor(obs.color))
        self.table.setItem(row, 4, color_item)

        self._refresh_observer_points()

    def _read_observers_from_table(self) -> List[Observer]:
        out: List[Observer] = []
        for row in range(self.table.rowCount()):
            try:
                enabled = self.table.item(row, 0).checkState() == Qt.CheckState.Checked
                lat = float(self.table.item(row, 1).text())
                lon = float(self.table.item(row, 2).text())
                alt = float(self.table.item(row, 3).text())
                color = self.table.item(row, 4).text().strip() or "#ff0000"
                out.append(Observer(enabled, lat, lon, alt, color))
            except Exception:
                continue
        return out

    def _refresh_observer_points(self):
        self.observer_layer.clear()
        observers = self._read_observers_from_table()
        for i, obs in enumerate(observers):
            style = PointStyle(
                radius=7.0,
                fill_color=obs.color,
                stroke_color="#000000",
                stroke_width=1.5,
            )
            self.observer_layer.add_points([(obs.lat, obs.lon)], ids=[f"obs_{i}"], style=style)

    def _add_observer(self):
        try:
            lat = float(self.lat_in.text())
            lon = float(self.lon_in.text())
            alt = float(self.alt_in.text())
        except ValueError:
            self.status.setText("Invalid observer input")
            return
        self._append_observer(Observer(True, lat, lon, alt, self.current_color))

    def _remove_selected(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self._refresh_observer_points()

    def _clear_viewshed(self):
        if self.viewshed_layer:
            self.viewshed_layer.remove()
            self.viewshed_layer = None

    def _compute_viewshed(self):
        if not self._map_ready:
            self.status.setText("Map still loading... wait for Ready.")
            return

        if self._worker_running:
            self.status.setText("Viewshed already running...")
            return

        self._refresh_observer_points()
        observers = [o for o in self._read_observers_from_table() if o.enabled]
        if not observers:
            self.status.setText("Enable at least one observer")
            return

        self.status.setText("Reading map extent...")
        self.progress.setValue(0)
        self._worker_running = True
        self._extent_pending = True
        self._extent_request_token += 1
        token = self._extent_request_token

        def on_extent_timeout():
            if token != self._extent_request_token:
                return
            if self._extent_pending:
                self._extent_pending = False
                self._worker_running = False
                self.status.setText(
                    "Could not read map extent (map may still be initializing). Try again."
                )

        QTimer.singleShot(20000, on_extent_timeout)

        def on_extent(ext):
            if token != self._extent_request_token:
                return
            self._extent_pending = False
            size = int(self.res_slider.value())
            render_mode = str(self.mode_combo.currentData())
            self._last_render_mode = render_mode
            extent_range_km = _haversine_m(
                float(ext["lat_min"]),
                float(ext["lon_min"]),
                float(ext["lat_max"]),
                float(ext["lon_max"]),
            ) / 1000.0
            self.status.setText("Computing viewshed...")
            self.progress.setValue(2)

            def worker():
                try:
                    def post_status(msg: str, pct: Optional[int] = None):
                        self.workerProgress.emit(msg, -1 if pct is None else int(pct))

                    zoom = max(8, min(12, int(ext.get("zoom", 10)) + 1))
                    post_status(f"Preparing DEM at z={zoom}...", 5)
                    dem = TerrainDEM(
                        ext,
                        zoom=zoom,
                        progress_cb=lambda m, p: post_status(
                            m, 5 + int((p or 0) * 0.40)
                        ),
                    )
                    png = _compute_viewshed_rgba(
                        dem,
                        ext,
                        observers,
                        size,
                        size,
                        render_mode=render_mode,
                        progress_cb=lambda m, p: post_status(
                            m, 45 + int((p or 0) * 0.53)
                        ),
                    )
                    bounds = [
                        (float(ext["lat_min"]), float(ext["lon_min"])),
                        (float(ext["lat_max"]), float(ext["lon_max"])),
                    ]
                    self.workerSuccess.emit(
                        png, bounds, len(observers), zoom, float(extent_range_km)
                    )
                except Exception as exc:
                    self.workerError.emit(str(exc))

            threading.Thread(target=worker, daemon=True).start()

        self.map_widget.get_view_extent(on_extent)


def main():
    app = QtWidgets.QApplication([])
    window = ViewshedWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
