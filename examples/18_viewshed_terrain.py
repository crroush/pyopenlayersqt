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
from typing import List, Tuple

import numpy as np
from PIL import Image
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, PointStyle, RasterStyle, XYZTileOptions

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
    def __init__(self, extent: dict, zoom: int):
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

        for ty in range(self.ty_min, self.ty_max + 1):
            for tx in range(self.tx_min, self.tx_max + 1):
                tile = self._fetch_tile(tx, ty)
                oy = (ty - self.ty_min) * 256
                ox = (tx - self.tx_min) * 256
                self.mosaic[oy : oy + 256, ox : ox + 256] = tile

    def _fetch_tile(self, tx: int, ty: int) -> np.ndarray:
        url = TERRARIUM_URL.format(z=self.zoom, x=tx, y=ty)
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        arr = np.asarray(img, dtype=np.float32)
        # Terrarium encoding: elevation = (R*256 + G + B/256) - 32768
        return (arr[:, :, 0] * 256.0 + arr[:, :, 1] + (arr[:, :, 2] / 256.0)) - 32768.0

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


def _is_visible(
    dem: TerrainDEM,
    obs_lat: float,
    obs_lon: float,
    obs_alt_m: float,
    tgt_lat: float,
    tgt_lon: float,
    tgt_offset_m: float = 1.7,
) -> bool:
    dist_m = _haversine_m(obs_lat, obs_lon, tgt_lat, tgt_lon)
    if dist_m < 1.0:
        return True

    obs_ground = dem.elevation_m(obs_lat, obs_lon)
    tgt_ground = dem.elevation_m(tgt_lat, tgt_lon)
    obs_h = obs_ground + obs_alt_m
    tgt_h = tgt_ground + tgt_offset_m

    # Step count scales with range; cap for speed.
    steps = int(max(8, min(120, dist_m / 120.0)))
    for i in range(1, steps):
        t = i / steps
        lat = obs_lat + (tgt_lat - obs_lat) * t
        lon = obs_lon + (tgt_lon - obs_lon) * t
        terrain_h = dem.elevation_m(lat, lon)
        los_h = obs_h + (tgt_h - obs_h) * t
        if terrain_h > los_h:
            return False
    return True


def _compute_viewshed_rgba(
    dem: TerrainDEM,
    extent: dict,
    observers: List[Observer],
    width_px: int,
    height_px: int,
) -> bytes:
    lon_min = float(extent["lon_min"])
    lon_max = float(extent["lon_max"])
    lat_min = float(extent["lat_min"])
    lat_max = float(extent["lat_max"])

    # Slightly inside pixel centers.
    lon_axis = np.linspace(lon_min, lon_max, width_px, dtype=np.float64)
    lat_axis = np.linspace(lat_max, lat_min, height_px, dtype=np.float64)

    r = np.zeros((height_px, width_px), dtype=np.uint16)
    g = np.zeros((height_px, width_px), dtype=np.uint16)
    b = np.zeros((height_px, width_px), dtype=np.uint16)
    a = np.zeros((height_px, width_px), dtype=np.uint16)

    for obs in observers:
        cr, cg, cb = _hex_to_rgb(obs.color)
        for iy, lat in enumerate(lat_axis):
            for ix, lon in enumerate(lon_axis):
                if _is_visible(dem, obs.lat, obs.lon, obs.eye_alt_m, float(lat), float(lon)):
                    r[iy, ix] += cr
                    g[iy, ix] += cg
                    b[iy, ix] += cb
                    a[iy, ix] += 90

    out = np.zeros((height_px, width_px, 4), dtype=np.uint8)
    out[:, :, 0] = np.clip(r, 0, 255).astype(np.uint8)
    out[:, :, 1] = np.clip(g, 0, 255).astype(np.uint8)
    out[:, :, 2] = np.clip(b, 0, 255).astype(np.uint8)
    out[:, :, 3] = np.clip(a, 0, 220).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(out, mode="RGBA").save(buf, format="PNG")
    return buf.getvalue()


class ViewshedWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Viewshed (AWS Terrain)")
        self.resize(1380, 860)

        self.map_widget = OLMapWidget(center=(39.5, -106.0), zoom=10)
        self.map_widget.add_xyz_tiles(
            XYZTileOptions(
                url=TERRARIUM_URL,
                opacity=0.65,
                min_zoom=0,
                max_zoom=15,
                attribution="Mapzen terrain tiles (AWS Open Data)",
            ),
            name="terrain",
        )

        self.observers: List[Observer] = []
        self.viewshed_layer = None
        self.observer_layer = self.map_widget.add_vector_layer("observers", selectable=False)
        self._worker_running = False

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
        self.res_slider.setValue(128)
        self.res_slider.setTickInterval(32)
        self.res_slider.valueChanged.connect(
            lambda v: self.res_label.setText(f"Raster size: {v} x {v}")
        )
        self.res_label = QtWidgets.QLabel("Raster size: 128 x 128")
        controls.addWidget(self.res_label)
        controls.addWidget(self.res_slider)

        compute_btn = QtWidgets.QPushButton("Compute Viewshed")
        compute_btn.clicked.connect(self._compute_viewshed)
        controls.addWidget(compute_btn)

        clear_btn = QtWidgets.QPushButton("Clear Raster")
        clear_btn.clicked.connect(self._clear_viewshed)
        controls.addWidget(clear_btn)

        self.status = QtWidgets.QLabel("Ready")
        controls.addWidget(self.status)
        controls.addStretch(1)

        self._seed_default_observers()

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
        if self._worker_running:
            self.status.setText("Viewshed already running...")
            return

        self._refresh_observer_points()
        observers = [o for o in self._read_observers_from_table() if o.enabled]
        if not observers:
            self.status.setText("Enable at least one observer")
            return

        self.status.setText("Reading map extent...")
        self._worker_running = True

        def on_extent(ext):
            size = int(self.res_slider.value())

            def worker():
                try:
                    zoom = max(8, min(14, int(ext.get("zoom", 10)) + 2))
                    dem = TerrainDEM(ext, zoom=zoom)
                    png = _compute_viewshed_rgba(dem, ext, observers, size, size)
                    bounds = [
                        (float(ext["lat_min"]), float(ext["lon_min"])),
                        (float(ext["lat_max"]), float(ext["lon_max"])),
                    ]

                    def apply_result():
                        if self.viewshed_layer is None:
                            self.viewshed_layer = self.map_widget.add_raster_image(
                                png, bounds=bounds, style=RasterStyle(opacity=0.75), name="viewshed"
                            )
                        else:
                            self.viewshed_layer.set_image(png, bounds=bounds)
                        self.status.setText(
                            f"Viewshed complete | observers={len(observers)} | z={zoom} | size={size}"
                        )
                        self._worker_running = False

                    QTimer.singleShot(0, apply_result)
                except Exception as exc:
                    def apply_error():
                        self.status.setText(f"Viewshed failed: {exc}")
                        self._worker_running = False

                    QTimer.singleShot(0, apply_error)

            threading.Thread(target=worker, daemon=True).start()

        self.map_widget.get_view_extent(on_extent)


def main():
    app = QtWidgets.QApplication([])
    window = ViewshedWindow()
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
