"""pyopenlayersqt demo (vector + FastPoints + FastGeo) with a scalable feature table.

Plumbing guarantees:
- "Clear fast points" clears fast points layer AND removes its rows from the table.
- "Clear fast geo" (next to it) clears fast geo layer AND removes its rows from the table.
- "Delete selected" removes from map + table (vector + fast points + fast geo).
"""

from __future__ import annotations

import sys
import time
import io
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image
from matplotlib import colors as mcolors
from matplotlib import colormaps
from matplotlib.path import Path as MplPath
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pyopenlayersqt import (
    CircleStyle,
    EllipseStyle,
    FastGeoPointsStyle,
    FastPointsStyle,
    OLMapWidget,
    PointStyle,
    PlotAxisConfig,
    PlotConfig,
    PlotTrace,
    PlotTraceStyle,
    PlotWidget,
    PolygonStyle,
    RasterStyle,
    WMSOptions,
)
from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget

LatLon = Tuple[float, float]


def rand_in_extent(ext: dict, rng: np.random.Generator) -> LatLon:
    """Generate random coordinate in extent. Returns (lat, lon) for public API."""
    lon = float(ext["lon_min"]) + rng.random() * (
        float(ext["lon_max"]) - float(ext["lon_min"])
    )
    lat = float(ext["lat_min"]) + rng.random() * (
        float(ext["lat_max"]) - float(ext["lat_min"])
    )
    return lat, lon  # Return lat,lon for public API


def random_polygon_in_extent(
    ext: dict, rng: np.random.Generator, n: int = 10
) -> List[LatLon]:
    """Return a simple (non-self-intersecting) ring inside extent as (lat, lon) tuples."""
    lat0, lon0 = rand_in_extent(ext, rng)
    # Use a small radius in degrees based on extent size.
    dx = float(ext["lon_max"]) - float(ext["lon_min"])
    dy = float(ext["lat_max"]) - float(ext["lat_min"])
    r0 = 0.15 * min(dx, dy)
    angles = np.sort(rng.random(max(4, n)) * (2.0 * np.pi))
    radii = (0.35 + 0.65 * rng.random(len(angles))) * r0
    ring = [
        (lat0 + float(np.sin(a) * r), lon0 + float(np.cos(a) * r))
        for a, r in zip(angles, radii)
    ]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def build_heatmap_png_bytes(
    *,
    ext: dict,
    rng: np.random.Generator,
    n_points: int = 250,
    grid_size: int = 512,
    colormap: str = "viridis",
    irregular_mask_ring: Optional[List[LatLon]] = None,
) -> bytes:
    """Simple IDW heatmap rendered to PNG RGBA bytes."""
    lon_min, lon_max = float(ext["lon_min"]), float(ext["lon_max"])
    lat_min, lat_max = float(ext["lat_min"]), float(ext["lat_max"])

    lons = lon_min + (lon_max - lon_min) * rng.random(n_points)
    lats = lat_min + (lat_max - lat_min) * rng.random(n_points)
    values = rng.random(n_points)

    gx = np.linspace(lon_min, lon_max, grid_size)
    gy = np.linspace(lat_min, lat_max, grid_size)
    grid_lon, grid_lat = np.meshgrid(gx, gy)

    eps = 1e-12
    d2 = (
        (grid_lon[..., None] - lons[None, None, :]) ** 2
        + (grid_lat[..., None] - lats[None, None, :]) ** 2
        + eps
    )
    w = 1.0 / d2
    z = (w * values[None, None, :]).sum(axis=2) / w.sum(axis=2)

    vmin = float(np.percentile(z, 2))
    vmax = float(np.percentile(z, 98))
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)
    cmap = colormaps.get_cmap(colormap)

    rgba = (cmap(norm(z), bytes=True)).astype(np.uint8)

    if irregular_mask_ring is not None and len(irregular_mask_ring) >= 4:
        pts = np.column_stack([grid_lon.ravel(), grid_lat.ravel()])
        # Convert mask ring from (lat, lon) to (lon, lat) for matplotlib Path
        ring_lonlat = [(lon, lat) for lat, lon in irregular_mask_ring]
        poly = MplPath(np.asarray(ring_lonlat, dtype=np.float64))
        inside = poly.contains_points(pts).reshape((grid_size, grid_size))
        rgba[~inside, 3] = 0

    img = Image.fromarray(rgba, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


class ShowcaseWindow(QMainWindow):
    """
    Demo window showcasing all pyopenlayersqt features.

    This comprehensive demo demonstrates vector layers, fast points,
    fast geo points, heatmaps, WMS layers, and feature tables.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("pyopenlayersqt Demo")
        self.resize(1650, 980)

        self._rng = np.random.default_rng(1234)
        self._last_extent: Optional[dict] = None

        self.mapw = OLMapWidget(center=(0.0, 0.0), zoom=2)
        self.mapw.ready.connect(self._on_ready)
        self.mapw.selectionChanged.connect(self._on_map_selection)
        self.mapw.watch_view_extent(self._on_extent_changed, debounce_ms=150)

        self.vector = self.mapw.add_vector_layer("vector", selectable=True)
        self.fast = self.mapw.add_fast_points_layer(
            "fast_points",
            selectable=True,
            style=FastPointsStyle(
                radius=2.5,
                default_rgba=(0, 180, 0, 180),
                selected_radius=6.0,
                selected_rgba=(255, 255, 0, 255),
            ),
            cell_size_m=750.0,
        )
        self.fast_geo = self.mapw.add_fast_geopoints_layer(
            "fast_geo",
            selectable=True,
            style=FastGeoPointsStyle(
                point_radius=2.5,
                default_point_rgba=(40, 80, 255, 180),
                selected_point_radius=6.0,
                selected_point_rgba=(255, 255, 255, 255),
                ellipse_stroke_rgba=(40, 80, 255, 160),
                ellipse_stroke_width=1.2,
                selected_ellipse_stroke_rgba=(255, 255, 255, 255),
                selected_ellipse_stroke_width=2.0,
                fill_ellipses=False,
                ellipse_fill_rgba=(40, 80, 255, 40),
                ellipses_visible=True,
                min_ellipse_px=0.0,
                max_ellipses_per_path=2000,
                skip_ellipses_while_interacting=True,
            ),
            cell_size_m=750.0,
        )

        self.wms_layer = None
        self.raster_layer = None
        self._heatmap_mask_ring = None  # type: Optional[List[LonLat]]

        self._build_ui()

    def _build_ui(self) -> None:
        root = QWidget()
        main = QHBoxLayout(root)

        left = QVBoxLayout()

        base_box = QGroupBox("Base map")
        base_row = QHBoxLayout(base_box)
        base_row.addWidget(QLabel("OSM opacity"))
        self.base_opacity_slider = QSlider(Qt.Horizontal)
        self.base_opacity_slider.setRange(0, 100)
        self.base_opacity_slider.setValue(100)
        self.base_opacity_label = QLabel("1.00")
        self.base_opacity_slider.valueChanged.connect(self._on_base_opacity)
        base_row.addWidget(self.base_opacity_slider, 1)
        base_row.addWidget(self.base_opacity_label)
        left.addWidget(base_box, 0)

        tabs = QTabWidget()
        tabs.addTab(self._tab_vector(), "Vector")
        tabs.addTab(self._tab_wms(), "WMS")
        tabs.addTab(self._tab_fast_points(), "FastPoints")
        tabs.addTab(self._tab_fast_geo(), "FastGeo")
        tabs.addTab(self._tab_heatmap(), "Heatmap")
        tabs.addTab(self._tab_plot(), "Plot")
        left.addWidget(tabs, 0)

        left.addWidget(self._build_table_box(), 1)
        main.addLayout(left, 0)
        
        # Right side: Map and Plot in vertical splitter
        from PySide6.QtWidgets import QSplitter
        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(self.mapw)
        
        # Create plot widget
        plot_config = PlotConfig(
            title="Feature Plot",
            x_axis=PlotAxisConfig(label="X", grid=True),
            y_axis=PlotAxisConfig(label="Y", grid=True),
            legend=True,
        )
        self.plot_widget = PlotWidget(config=plot_config)
        self.plot_widget.selectionChanged.connect(self._on_plot_selection)
        right_splitter.addWidget(self.plot_widget)
        
        # Set initial sizes (map larger than plot)
        right_splitter.setSizes([600, 300])
        
        main.addWidget(right_splitter, 1)
        self.setCentralWidget(root)

    def _build_table_box(self) -> QWidget:
        box = QGroupBox("Features")
        layout = QVBoxLayout(box)

        columns = [
            ColumnSpec("Layer", lambda r: r.get("layer_kind", "")),
            ColumnSpec("Type", lambda r: r.get("geom_type", "")),
            ColumnSpec("Feature ID", lambda r: r.get("feature_id", "")),
            ColumnSpec(
                "Center lat",
                lambda r: r.get("center_lat", ""),
                fmt=lambda v: f"{float(v):.6f}" if v != "" else "",
            ),
            ColumnSpec(
                "Center lon",
                lambda r: r.get("center_lon", ""),
                fmt=lambda v: f"{float(v):.6f}" if v != "" else "",
            ),
            ColumnSpec("Layer ID", lambda r: r.get("layer_id", "")),
        ]

        self.tablew = FeatureTableWidget(
            columns=columns,
            key_fn=lambda r: (str(r.get("layer_id", "")), str(r.get("feature_id", ""))),
            debounce_ms=90,
        )
        self.model = self.tablew.model
        self.tablew.selectionKeysChanged.connect(self._on_table_selection_changed)
        layout.addWidget(self.tablew)

        btn_row = QHBoxLayout()
        b_vec = QPushButton("Clear vector")
        b_vec.clicked.connect(self._clear_vector)
        btn_row.addWidget(b_vec)

        b_fp = QPushButton("Clear fast points")
        b_fp.clicked.connect(self._clear_fast_points)
        btn_row.addWidget(b_fp)

        b_fgp = QPushButton("Clear fast geo")
        b_fgp.clicked.connect(self._clear_fast_geo)
        btn_row.addWidget(b_fgp)

        b_tbl = QPushButton("Clear heatmap")
        b_tbl.clicked.connect(self._remove_heatmap_overlay)
        btn_row.addWidget(b_tbl)

        b_del = QPushButton("Delete selected")
        b_del.clicked.connect(self._delete_selected)
        btn_row.addWidget(b_del)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        return box

    def _tab_vector(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # Layer controls
        controls_box = QGroupBox("Vector layer controls")
        controls_layout = QVBoxLayout(controls_box)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity:"))
        self.vec_opacity_slider = QSlider(Qt.Horizontal)
        self.vec_opacity_slider.setRange(0, 100)
        self.vec_opacity_slider.setValue(100)
        self.vec_opacity_label = QLabel("1.00")
        self.vec_opacity_slider.valueChanged.connect(self._on_vector_opacity)
        opacity_row.addWidget(self.vec_opacity_slider, 1)
        opacity_row.addWidget(self.vec_opacity_label)
        controls_layout.addLayout(opacity_row)

        vis_row = QHBoxLayout()
        self.vec_visible = QCheckBox("Visible")
        self.vec_visible.setChecked(True)
        self.vec_visible.toggled.connect(lambda on: self.vector.set_visible(bool(on)))
        vis_row.addWidget(self.vec_visible)

        self.vec_selectable = QCheckBox("Selectable")
        self.vec_selectable.setChecked(True)
        self.vec_selectable.toggled.connect(lambda on: self.vector.set_selectable(bool(on)))
        vis_row.addWidget(self.vec_selectable)
        vis_row.addStretch(1)
        controls_layout.addLayout(vis_row)

        layout.addWidget(controls_box)

        style_box = QGroupBox("Vector style")
        form = QFormLayout(style_box)

        # Stroke color picker
        self.vec_stroke_color = QColor("#00aaff")
        self.vec_stroke_btn = QPushButton()
        self.vec_stroke_btn.setStyleSheet(f"background-color: {self.vec_stroke_color.name()}")
        self.vec_stroke_btn.setMaximumWidth(100)
        self.vec_stroke_btn.clicked.connect(self._choose_stroke_color)
        form.addRow("Stroke color", self.vec_stroke_btn)

        self.vec_stroke_w = QDoubleSpinBox()
        self.vec_stroke_w.setRange(0.0, 10.0)
        self.vec_stroke_w.setValue(2.0)
        self.vec_stroke_w.setSingleStep(0.5)
        form.addRow("Stroke width", self.vec_stroke_w)

        # Fill color picker
        self.vec_fill_color = QColor("#00aaff")
        self.vec_fill_btn = QPushButton()
        self.vec_fill_btn.setStyleSheet(f"background-color: {self.vec_fill_color.name()}")
        self.vec_fill_btn.setMaximumWidth(100)
        self.vec_fill_btn.clicked.connect(self._choose_fill_color)
        form.addRow("Fill color", self.vec_fill_btn)

        self.vec_fill_op = QDoubleSpinBox()
        self.vec_fill_op.setRange(0.0, 1.0)
        self.vec_fill_op.setValue(0.15)
        self.vec_fill_op.setSingleStep(0.05)
        form.addRow("Fill opacity", self.vec_fill_op)
        layout.addWidget(style_box)

        ellipse_box = QGroupBox("Ellipse params (meters, degrees)")
        ef = QFormLayout(ellipse_box)
        self.ellipse_random = QCheckBox("Randomize SMA/SMI/Tilt")
        self.ellipse_random.setChecked(True)
        self.ellipse_sma = QDoubleSpinBox()
        self.ellipse_sma.setRange(1.0, 1_000_000.0)
        self.ellipse_sma.setValue(2000.0)
        self.ellipse_smi = QDoubleSpinBox()
        self.ellipse_smi.setRange(1.0, 1_000_000.0)
        self.ellipse_smi.setValue(1200.0)
        self.ellipse_tilt = QDoubleSpinBox()
        self.ellipse_tilt.setRange(0.0, 180.0)
        self.ellipse_tilt.setValue(90.0)
        ef.addRow(self.ellipse_random)
        ef.addRow("SMA (m)", self.ellipse_sma)
        ef.addRow("SMI (m)", self.ellipse_smi)
        ef.addRow("Tilt (deg from true north)", self.ellipse_tilt)
        layout.addWidget(ellipse_box)

        btns = QHBoxLayout()
        b_pt = QPushButton("Add point")
        b_pt.clicked.connect(self._add_vector_point)
        btns.addWidget(b_pt)
        b_el = QPushButton("Add ellipse")
        b_el.clicked.connect(self._add_vector_ellipse)
        btns.addWidget(b_el)
        b_ci = QPushButton("Add circle")
        b_ci.clicked.connect(self._add_vector_circle)
        btns.addWidget(b_ci)
        b_po = QPushButton("Add polygon")
        b_po.clicked.connect(self._add_vector_polygon)
        btns.addWidget(b_po)
        b_ln = QPushButton("Add line")
        b_ln.clicked.connect(self._add_vector_line)
        btns.addWidget(b_ln)
        layout.addLayout(btns)
        layout.addStretch(1)
        return w

    def _tab_wms(self) -> QWidget:
        """WMS overlay controls."""
        w = QWidget()
        layout = QVBoxLayout(w)

        src_box = QGroupBox("WMS source")
        form = QFormLayout(src_box)

        # A public demo endpoint that is convenient for quick testing.
        self.wms_url = QLineEdit("https://ahocevar.com/geoserver/wms")
        self.wms_layers = QLineEdit("topp:states")

        self.wms_format = QComboBox()
        self.wms_format.addItems(["image/png", "image/jpeg"])

        self.wms_transparent = QCheckBox("TRANSPARENT")
        self.wms_transparent.setChecked(True)

        form.addRow("URL", self.wms_url)
        form.addRow("LAYERS", self.wms_layers)
        form.addRow("FORMAT", self.wms_format)
        form.addRow(self.wms_transparent)

        layout.addWidget(src_box)

        op_box = QGroupBox("WMS opacity")
        op_row = QHBoxLayout(op_box)
        self.wms_opacity_slider = QSlider(Qt.Horizontal)
        self.wms_opacity_slider.setRange(0, 100)
        self.wms_opacity_slider.setValue(85)
        self.wms_opacity_label = QLabel("0.85")
        self.wms_opacity_slider.valueChanged.connect(self._on_wms_opacity)
        op_row.addWidget(self.wms_opacity_slider, 1)
        op_row.addWidget(self.wms_opacity_label)
        layout.addWidget(op_box)

        btn_row = QHBoxLayout()
        b_add = QPushButton("Add/Update WMS")
        b_add.clicked.connect(self._add_or_update_wms)
        btn_row.addWidget(b_add)

        b_rm = QPushButton("Remove WMS")
        b_rm.clicked.connect(self._remove_wms)
        btn_row.addWidget(b_rm)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        layout.addStretch(1)
        return w

    def _wms_opacity_value(self) -> float:
        return float(self.wms_opacity_slider.value()) / 100.0

    def _on_wms_opacity(self, v: int) -> None:
        op = float(v) / 100.0
        self.wms_opacity_label.setText(f"{op:.2f}")
        if self.wms_layer is not None:
            self.wms_layer.set_opacity(op)

    def _add_or_update_wms(self) -> None:
        url = self.wms_url.text().strip()
        layers = self.wms_layers.text().strip()
        fmt = str(self.wms_format.currentText())
        transparent = bool(self.wms_transparent.isChecked())
        op = self._wms_opacity_value()

        if not url or not layers:
            QMessageBox.information(self, "WMS", "Please set URL and LAYERS.")
            return

        opt = WMSOptions(
            url=url,
            params={
                "LAYERS": layers,
                "TILED": True,
                "FORMAT": fmt,
                "TRANSPARENT": transparent,
            },
            opacity=op,
        )

        # simplest: remove and re-add, so URL/LAYERS updates always apply.
        if self.wms_layer is not None:
            try:
                self.wms_layer.remove()
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            self.wms_layer = None

        self.wms_layer = self.mapw.add_wms(opt, name="wms")
        self._status("WMS: added/updated")

    def _remove_wms(self) -> None:
        if self.wms_layer is None:
            return
        self.wms_layer.remove()
        self.wms_layer = None
        self._status("WMS: removed")

    def _tab_fast_points(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # Layer controls
        controls_box = QGroupBox("FastPoints layer controls")
        controls_layout = QVBoxLayout(controls_box)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity:"))
        self.fast_opacity_slider = QSlider(Qt.Horizontal)
        self.fast_opacity_slider.setRange(0, 100)
        self.fast_opacity_slider.setValue(100)
        self.fast_opacity_label = QLabel("1.00")
        self.fast_opacity_slider.valueChanged.connect(self._on_fast_opacity)
        opacity_row.addWidget(self.fast_opacity_slider, 1)
        opacity_row.addWidget(self.fast_opacity_label)
        controls_layout.addLayout(opacity_row)

        vis_row = QHBoxLayout()
        self.fast_visible = QCheckBox("Visible")
        self.fast_visible.setChecked(True)
        self.fast_visible.toggled.connect(lambda on: self.fast.set_visible(bool(on)))
        vis_row.addWidget(self.fast_visible)

        self.fast_selectable = QCheckBox("Selectable")
        self.fast_selectable.setChecked(True)
        self.fast_selectable.toggled.connect(lambda on: self.fast.set_selectable(bool(on)))
        vis_row.addWidget(self.fast_selectable)
        vis_row.addStretch(1)
        controls_layout.addLayout(vis_row)

        layout.addWidget(controls_box)

        row = QHBoxLayout()
        row.addWidget(QLabel("N"))
        self.fast_n = QSpinBox()
        self.fast_n.setRange(1000, 5_000_000)
        self.fast_n.setSingleStep(50_000)
        self.fast_n.setValue(200_000)
        row.addWidget(self.fast_n)
        self.fast_color_mode = QComboBox()
        self.fast_color_mode.addItems(["single color", "per-point RGBA"])
        row.addWidget(self.fast_color_mode)
        btn = QPushButton("Add random fast points in extent")
        btn.clicked.connect(self._add_fast_points)
        row.addWidget(btn)
        layout.addLayout(row)
        layout.addStretch(1)
        return w

    def _tab_fast_geo(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        # Layer controls
        controls_box = QGroupBox("FastGeo layer controls")
        controls_layout = QVBoxLayout(controls_box)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity:"))
        self.fgp_opacity_slider = QSlider(Qt.Horizontal)
        self.fgp_opacity_slider.setRange(0, 100)
        self.fgp_opacity_slider.setValue(100)
        self.fgp_opacity_label = QLabel("1.00")
        self.fgp_opacity_slider.valueChanged.connect(self._on_fgp_opacity)
        opacity_row.addWidget(self.fgp_opacity_slider, 1)
        opacity_row.addWidget(self.fgp_opacity_label)
        controls_layout.addLayout(opacity_row)

        vis_row = QHBoxLayout()
        self.fgp_visible = QCheckBox("Visible")
        self.fgp_visible.setChecked(True)
        self.fgp_visible.toggled.connect(lambda on: self.fast_geo.set_visible(bool(on)))
        vis_row.addWidget(self.fgp_visible)

        self.fgp_selectable = QCheckBox("Selectable")
        self.fgp_selectable.setChecked(True)
        self.fgp_selectable.toggled.connect(lambda on: self.fast_geo.set_selectable(bool(on)))
        vis_row.addWidget(self.fgp_selectable)
        vis_row.addStretch(1)
        controls_layout.addLayout(vis_row)

        layout.addWidget(controls_box)

        row = QHBoxLayout()
        row.addWidget(QLabel("N"))
        self.fgp_n = QSpinBox()
        self.fgp_n.setRange(1000, 5_000_000)
        self.fgp_n.setSingleStep(50_000)
        self.fgp_n.setValue(100_000)
        row.addWidget(self.fgp_n)
        self.fgp_show_ellipses = QCheckBox("Show ellipses")
        self.fgp_show_ellipses.setChecked(True)
        self.fgp_show_ellipses.toggled.connect(
            lambda on: self.fast_geo.set_ellipses_visible(bool(on))
        )
        row.addWidget(self.fgp_show_ellipses)
        btn = QPushButton("Add random fast geo points (with ellipses) in extent")
        btn.clicked.connect(self._add_fast_geo)
        row.addWidget(btn)
        layout.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("SMA (m):"))
        self.fgp_sma_min = QDoubleSpinBox()
        self.fgp_sma_min.setRange(0.0, 1e7)
        self.fgp_sma_min.setValue(25.0)
        self.fgp_sma_max = QDoubleSpinBox()
        self.fgp_sma_max.setRange(0.0, 1e7)
        self.fgp_sma_max.setValue(250.0)
        row2.addWidget(self.fgp_sma_min)
        row2.addWidget(QLabel("to"))
        row2.addWidget(self.fgp_sma_max)
        row2.addSpacing(20)
        row2.addWidget(QLabel("SMI (m):"))
        self.fgp_smi_min = QDoubleSpinBox()
        self.fgp_smi_min.setRange(0.0, 1e7)
        self.fgp_smi_min.setValue(10.0)
        self.fgp_smi_max = QDoubleSpinBox()
        self.fgp_smi_max.setRange(0.0, 1e7)
        self.fgp_smi_max.setValue(120.0)
        row2.addWidget(self.fgp_smi_min)
        row2.addWidget(QLabel("to"))
        row2.addWidget(self.fgp_smi_max)
        row2.addStretch(1)
        layout.addLayout(row2)
        layout.addStretch(1)
        return w

    # ---- callbacks / helpers ----
    def _status(self, msg: str) -> None:
        print(msg, flush=True)

    def _tab_heatmap(self) -> QWidget:
        """Heatmap overlay controls (PNG bytes raster overlay)."""
        w = QWidget()
        layout = QVBoxLayout(w)

        opts_box = QGroupBox("Heatmap options")
        form = QFormLayout(opts_box)

        self.heat_npts = QSpinBox()
        self.heat_npts.setRange(50, 5000)
        self.heat_npts.setValue(250)
        form.addRow("Sample points (irregular)", self.heat_npts)

        self.heat_gridsz = QSpinBox()
        self.heat_gridsz.setRange(128, 2048)
        self.heat_gridsz.setSingleStep(128)
        self.heat_gridsz.setValue(512)
        form.addRow("Grid size (px)", self.heat_gridsz)

        self.heat_cmap = QComboBox()
        self.heat_cmap.addItems(["viridis", "plasma", "inferno", "magma", "turbo"])
        form.addRow("Colormap", self.heat_cmap)

        self.heat_use_mask = QCheckBox("Clip to irregular polygon (alpha mask)")
        self.heat_use_mask.setChecked(True)
        form.addRow(self.heat_use_mask)

        mask_row = QHBoxLayout()
        btn_new_mask = QPushButton("New random mask polygon")
        btn_new_mask.clicked.connect(self._new_heatmap_mask_polygon)
        mask_row.addWidget(btn_new_mask)

        btn_clear_mask = QPushButton("Clear mask (use full extent)")
        btn_clear_mask.clicked.connect(self._clear_heatmap_mask_polygon)
        mask_row.addWidget(btn_clear_mask)
        mask_row.addStretch(1)
        form.addRow("Mask", mask_row)

        layout.addWidget(opts_box)

        op_box = QGroupBox("Heatmap overlay opacity")
        op_row = QHBoxLayout(op_box)
        self.heat_opacity_slider = QSlider(Qt.Horizontal)
        self.heat_opacity_slider.setRange(0, 100)
        self.heat_opacity_slider.setValue(55)
        self.heat_opacity_label = QLabel("0.55")
        self.heat_opacity_slider.valueChanged.connect(self._on_heatmap_opacity)
        op_row.addWidget(self.heat_opacity_slider, 1)
        op_row.addWidget(self.heat_opacity_label)
        layout.addWidget(op_box)

        btn_row = QHBoxLayout()
        btn_build = QPushButton("Build/Update heatmap overlay")
        btn_build.clicked.connect(self._build_heatmap_overlay)
        btn_row.addWidget(btn_build)

        btn_remove = QPushButton("Remove heatmap overlay")
        btn_remove.clicked.connect(self._remove_heatmap_overlay)
        btn_row.addWidget(btn_remove)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        layout.addWidget(
            QLabel(
                "Builds a PNG in Python and draws it as a raster overlay. "
                "If clip is enabled, pixels outside the mask polygon are alpha=0."
            )
        )
        layout.addStretch(1)
        return w

    def _heatmap_opacity_value(self) -> float:
        return float(self.heat_opacity_slider.value()) / 100.0

    def _on_heatmap_opacity(self, v: int) -> None:
        op = float(v) / 100.0
        self.heat_opacity_label.setText(f"{op:.2f}")
        if self.raster_layer is not None:
            self.raster_layer.set_opacity(op)

    def _new_heatmap_mask_polygon(self) -> None:
        ext = self._require_extent()
        self._heatmap_mask_ring = random_polygon_in_extent(ext, self._rng, n=10)
        self._status("HEATMAP: generated new random mask polygon")

    def _clear_heatmap_mask_polygon(self) -> None:
        self._heatmap_mask_ring = None
        self._status("HEATMAP: cleared mask polygon (full extent)")

    def _build_heatmap_overlay(self) -> None:
        ext = self._require_extent()
        mask = self._heatmap_mask_ring if self.heat_use_mask.isChecked() else None

        png = build_heatmap_png_bytes(
            ext=ext,
            rng=self._rng,
            n_points=int(self.heat_npts.value()),
            grid_size=int(self.heat_gridsz.value()),
            colormap=str(self.heat_cmap.currentText()),
            irregular_mask_ring=mask,
        )

        bounds = [
            (float(ext["lat_min"]), float(ext["lon_min"])),
            (float(ext["lat_max"]), float(ext["lon_max"])),
        ]

        op = self._heatmap_opacity_value()

        if self.raster_layer is None:
            self.raster_layer = self.mapw.add_raster_image(
                png,
                bounds=bounds,
                style=RasterStyle(opacity=op),
                name="heatmap",
            )
        else:
            self.raster_layer.remove()
            self.raster_layer = self.mapw.add_raster_image(
                png,
                bounds=bounds,
                style=RasterStyle(opacity=op),
                name="heatmap",
            )

        self._status("HEATMAP: overlay updated")

    def _remove_heatmap_overlay(self) -> None:
        if self.raster_layer is None:
            return
        self.raster_layer.remove()
        self.raster_layer = None
        self._status("HEATMAP: removed overlay")

    def _tab_plot(self) -> QWidget:
        """Plot controls for scatter/time-series visualization."""
        w = QWidget()
        layout = QVBoxLayout(w)

        info_label = QLabel(
            "The plot widget shows lat vs lon for fast points. "
            "Click on points in the plot to select them (syncs with map & table)."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Plot data controls
        data_box = QGroupBox("Plot Data")
        data_layout = QVBoxLayout(data_box)

        btn_row = QHBoxLayout()
        btn_plot_fast = QPushButton("Plot Fast Points (Lat vs Lon)")
        btn_plot_fast.clicked.connect(self._plot_fast_points)
        btn_row.addWidget(btn_plot_fast)

        btn_clear_plot = QPushButton("Clear Plot")
        btn_clear_plot.clicked.connect(self._clear_plot)
        btn_row.addWidget(btn_clear_plot)
        
        btn_row.addStretch()
        data_layout.addLayout(btn_row)

        layout.addWidget(data_box)

        # Plot styling
        style_box = QGroupBox("Plot Style")
        style_layout = QFormLayout(style_box)

        self.plot_point_size = QDoubleSpinBox()
        self.plot_point_size.setRange(1.0, 20.0)
        self.plot_point_size.setValue(4.0)
        style_layout.addRow("Point Size", self.plot_point_size)

        self.plot_alpha = QDoubleSpinBox()
        self.plot_alpha.setRange(0.0, 1.0)
        self.plot_alpha.setSingleStep(0.1)
        self.plot_alpha.setValue(0.6)
        style_layout.addRow("Alpha (Opacity)", self.plot_alpha)

        self.plot_color = QComboBox()
        self.plot_color.addItems(["Blue", "Red", "Green", "Orange", "Purple"])
        style_layout.addRow("Color", self.plot_color)

        layout.addWidget(style_box)

        # Action buttons
        action_box = QGroupBox("Plot Actions")
        action_layout = QVBoxLayout(action_box)

        btn_auto_range = QPushButton("Auto Range")
        btn_auto_range.clicked.connect(lambda: self.plot_widget.auto_range())
        action_layout.addWidget(btn_auto_range)

        layout.addWidget(action_box)

        layout.addStretch(1)
        return w

    def _plot_fast_points(self) -> None:
        """Create a scatter plot of fast points (lat vs lon)."""
        # Get all fast points from the table
        rows = []
        for i in range(self.model.rowCount()):
            row_data = self.model._rows[i]
            if row_data.get("layer_kind") == "fast_points":
                rows.append(row_data)

        if not rows:
            QMessageBox.information(
                self, "No Data", "Add some fast points first (FastPoints tab)."
            )
            return

        # Extract data
        lats = [r["center_lat"] for r in rows]
        lons = [r["center_lon"] for r in rows]
        fids = [r["feature_id"] for r in rows]
        layer_id = rows[0]["layer_id"]

        # Map color name to hex
        color_map = {
            "Blue": "#4285F4",
            "Red": "#EA4335",
            "Green": "#34A853",
            "Orange": "#FBBC04",
            "Purple": "#9C27B0",
        }
        color = color_map.get(str(self.plot_color.currentText()), "#4285F4")

        # Create trace style
        style = PlotTraceStyle(
            color=color,
            point_size=float(self.plot_point_size.value()),
            symbol="o",
            show_points=True,
            show_line=False,
            alpha=float(self.plot_alpha.value()),
        )

        # Create trace
        trace = PlotTrace(
            name="Fast Points",
            x_data=tuple(lons),
            y_data=tuple(lats),
            feature_ids=tuple(fids),
            layer_id=layer_id,
            style=style,
        )

        # Add to plot
        self.plot_widget.add_trace(trace)
        self.plot_widget.auto_range()

        self._status(f"PLOT: Added {len(rows)} points to plot")

    def _clear_plot(self) -> None:
        """Clear all traces from the plot."""
        self.plot_widget.clear_traces()
        self._status("PLOT: Cleared all traces")

    def _on_ready(self) -> None:
        self._status("MAP: ready")

    def _on_extent_changed(self, ext: dict) -> None:
        print(f"extent changed {ext}")
        self._last_extent = ext

    def _require_extent(self) -> dict:
        if self._last_extent is None:
            QMessageBox.information(
                self, "Extent not ready", "Pan/zoom the map once, then try again."
            )
            raise RuntimeError("Extent not ready")
        return self._last_extent

    def _on_base_opacity(self, v: int) -> None:
        op = float(v) / 100.0
        self.base_opacity_label.setText(f"{op:.2f}")
        self.mapw.set_base_opacity(op)

    def _on_vector_opacity(self, v: int) -> None:
        op = float(v) / 100.0
        self.vec_opacity_label.setText(f"{op:.2f}")
        self.vector.set_opacity(op)

    def _on_fast_opacity(self, v: int) -> None:
        op = float(v) / 100.0
        self.fast_opacity_label.setText(f"{op:.2f}")
        self.fast.set_opacity(op)

    def _on_fgp_opacity(self, v: int) -> None:
        op = float(v) / 100.0
        self.fgp_opacity_label.setText(f"{op:.2f}")
        self.fast_geo.set_opacity(op)

    def _choose_stroke_color(self) -> None:
        """Open color picker for stroke color."""
        color = QColorDialog.getColor(self.vec_stroke_color, self, "Choose Stroke Color")
        if color.isValid():
            self.vec_stroke_color = color
            self.vec_stroke_btn.setStyleSheet(f"background-color: {color.name()}")

    def _choose_fill_color(self) -> None:
        """Open color picker for fill color."""
        color = QColorDialog.getColor(self.vec_fill_color, self, "Choose Fill Color")
        if color.isValid():
            self.vec_fill_color = color
            self.vec_fill_btn.setStyleSheet(f"background-color: {color.name()}")

    # ---- styles ----
    def _poly_style(self) -> PolygonStyle:
        return PolygonStyle(
            stroke_color=self.vec_stroke_color.name(),
            stroke_width=float(self.vec_stroke_w.value()),
            fill_color=self.vec_fill_color.name(),
            fill_opacity=float(self.vec_fill_op.value()),
            fill=True,
        )

    def _ellipse_style(self) -> EllipseStyle:
        ps = self._poly_style()
        return EllipseStyle(
            stroke_color=ps.stroke_color,
            stroke_width=ps.stroke_width,
            stroke_opacity=0.95,
            fill_color=ps.fill_color,
            fill_opacity=ps.fill_opacity,
            fill=True,
        )

    def _circle_style(self) -> CircleStyle:
        ps = self._poly_style()
        return CircleStyle(
            stroke_color=ps.stroke_color,
            stroke_width=ps.stroke_width,
            stroke_opacity=0.95,
            fill_color=ps.fill_color,
            fill_opacity=ps.fill_opacity,
            fill=True,
        )

    def _point_style(self) -> PointStyle:
        return PointStyle(
            radius=6.0,
            fill_color=self.vec_fill_color.name(),
            fill_opacity=min(1.0, float(self.vec_fill_op.value()) + 0.2),
            stroke_color=self.vec_stroke_color.name(),
            stroke_width=max(1.0, float(self.vec_stroke_w.value())),
            stroke_opacity=0.9,
        )

    # ---- vector actions ----
    def _add_vector_point(self) -> None:
        ext = self._require_extent()
        lat, lon = rand_in_extent(ext, self._rng)
        fid = f"pt_{int(time.time()*1000)}"
        self.vector.add_points([(lat, lon)], ids=[fid], style=self._point_style())
        self.tablew.append_rows(
            [
                {
                    "layer_kind": "vector",
                    "layer_id": self.vector.id,
                    "feature_id": fid,
                    "geom_type": "point",
                    "center_lat": lat,
                    "center_lon": lon,
                }
            ]
        )

    def _add_vector_circle(self) -> None:
        ext = self._require_extent()
        lat, lon = rand_in_extent(ext, self._rng)
        fid = f"circle_{int(time.time()*1000)}"
        radius_m = 250.0 + 1500.0 * self._rng.random()
        self.vector.add_circle(
            (lat, lon), radius_m, feature_id=fid, style=self._circle_style()
        )
        self.tablew.append_rows(
            [
                {
                    "layer_kind": "vector",
                    "layer_id": self.vector.id,
                    "feature_id": fid,
                    "geom_type": "circle",
                    "center_lat": lat,
                    "center_lon": lon,
                }
            ]
        )

    def _add_vector_ellipse(self) -> None:
        ext = self._require_extent()
        lat, lon = rand_in_extent(ext, self._rng)
        fid = f"ell_{int(time.time()*1000)}"
        if self.ellipse_random.isChecked():
            sma = 400.0 + 2500.0 * self._rng.random()
            smi = 200.0 + 1500.0 * self._rng.random()
            tilt = float(self._rng.random() * 180.0)
            self.ellipse_sma.setValue(float(sma))
            self.ellipse_smi.setValue(float(smi))
            self.ellipse_tilt.setValue(float(tilt))
        else:
            sma = float(self.ellipse_sma.value())
            smi = float(self.ellipse_smi.value())
            tilt = float(self.ellipse_tilt.value())
        self.vector.add_ellipse(
            (lat, lon),
            sma,
            smi,
            tilt,
            feature_id=fid,
            style=self._ellipse_style(),
            properties={"sma_m": sma, "smi_m": smi, "tilt_deg": tilt},
        )
        self.tablew.append_rows(
            [
                {
                    "layer_kind": "vector",
                    "layer_id": self.vector.id,
                    "feature_id": fid,
                    "geom_type": "ellipse",
                    "center_lat": lat,
                    "center_lon": lon,
                }
            ]
        )

    def _add_vector_polygon(self) -> None:
        ext = self._require_extent()
        lon0, lat0 = rand_in_extent(ext, self._rng)
        fid = f"poly_{int(time.time()*1000)}"
        angles = np.sort(self._rng.random(8) * (2.0 * np.pi))
        radii = 0.002 + 0.01 * self._rng.random(8)
        ring = [
            (lon0 + float(np.cos(a) * r), lat0 + float(np.sin(a) * r))
            for a, r in zip(angles, radii)
        ]
        ring.append(ring[0])
        self.vector.add_polygon(ring, feature_id=fid, style=self._poly_style())
        self.tablew.append_rows(
            [
                {
                    "layer_kind": "vector",
                    "layer_id": self.vector.id,
                    "feature_id": fid,
                    "geom_type": "polygon",
                    "center_lat": lat0,
                    "center_lon": lon0,
                }
            ]
        )

    def _add_vector_line(self) -> None:
        ext = self._require_extent()
        lon0, lat0 = rand_in_extent(ext, self._rng)
        fid = f"line_{int(time.time()*1000)}"
        n = 3 + int(self._rng.integers(0, 4))
        angles = np.sort(self._rng.random(n) * (2.0 * np.pi))
        radii = 0.001 + 0.01 * self._rng.random(n)
        coords = [
            (lat0 + float(np.sin(a) * r), lon0 + float(np.cos(a) * r))
            for a, r in zip(angles, radii)
        ]
        self.vector.add_line(coords, feature_id=fid, style=self._poly_style())
        self.tablew.append_rows(
            [
                {
                    "layer_kind": "vector",
                    "layer_id": self.vector.id,
                    "feature_id": fid,
                    "geom_type": "line",
                    "center_lat": lat0,
                    "center_lon": lon0,
                }
            ]
        )

    # ---- fast actions ----
    def _add_fast_points(self) -> None:
        ext = self._require_extent()
        n = int(self.fast_n.value())
        lon_min, lon_max = float(ext["lon_min"]), float(ext["lon_max"])
        lat_min, lat_max = float(ext["lat_min"]), float(ext["lat_max"])
        lons = lon_min + self._rng.random(n) * (lon_max - lon_min)
        lats = lat_min + self._rng.random(n) * (lat_max - lat_min)
        coords = list(zip(lats.tolist(), lons.tolist()))  # (lat, lon) for public API
        ids = [f"fp{i}" for i in range(n)]
        colors = None
        if self.fast_color_mode.currentIndex() == 1:
            rgba = self._rng.integers(0, 256, size=(n, 4), dtype=np.int32)
            rgba[:, 3] = 200
            colors = [tuple(map(int, row)) for row in rgba]
        self.fast.add_points(coords, ids=ids, colors_rgba=colors)
        rows = (
            {
                "layer_kind": "fast_points",
                "layer_id": self.fast.id,
                "feature_id": ids[i],
                "geom_type": "point",
                "center_lat": float(lats[i]),
                "center_lon": float(lons[i]),
            }
            for i in range(n)
        )
        self.model.append_rows(rows)

    def _add_fast_geo(self) -> None:
        ext = self._require_extent()
        n = int(self.fgp_n.value())
        lon_min, lon_max = float(ext["lon_min"]), float(ext["lon_max"])
        lat_min, lat_max = float(ext["lat_min"]), float(ext["lat_max"])
        lons = lon_min + self._rng.random(n) * (lon_max - lon_min)
        lats = lat_min + self._rng.random(n) * (lat_max - lat_min)
        coords = list(zip(lats.tolist(), lons.tolist()))  # (lat, lon) for public API
        sma_min, sma_max = float(self.fgp_sma_min.value()), float(
            self.fgp_sma_max.value()
        )
        smi_min, smi_max = float(self.fgp_smi_min.value()), float(
            self.fgp_smi_max.value()
        )
        sma = sma_min + self._rng.random(n) * max(1e-9, (sma_max - sma_min))
        smi = smi_min + self._rng.random(n) * max(1e-9, (smi_max - smi_min))
        sma2 = np.maximum(sma, smi)
        smi2 = np.minimum(sma, smi)
        sma, smi = sma2, smi2
        tilt = self._rng.random(n) * 360.0
        ids = [f"fgp{i}" for i in range(n)]
        self.fast_geo.add_points_with_ellipses(
            coords,
            sma_m=sma.tolist(),
            smi_m=smi.tolist(),
            tilt_deg=tilt.tolist(),
            ids=ids,
        )
        rows = (
            {
                "layer_kind": "fast_geo",
                "layer_id": self.fast_geo.id,
                "feature_id": ids[i],
                "geom_type": "point+ellipse",
                "center_lat": float(lats[i]),
                "center_lon": float(lons[i]),
            }
            for i in range(n)
        )
        self.model.append_rows(rows)

    # ---- delete / clear ----
    def _delete_selected(self) -> None:
        keys = self.tablew.selected_keys()
        if not keys:
            return
        by_layer: Dict[str, List[str]] = {}
        for layer_id, fid in keys:
            by_layer.setdefault(str(layer_id), []).append(str(fid))
        for layer_id, fids in by_layer.items():
            if layer_id == str(self.vector.id):
                self.vector.remove_features(fids)
            elif layer_id == str(self.fast.id):
                self.fast.remove_points(fids)
            elif layer_id == str(self.fast_geo.id):
                self.fast_geo.remove_ids(fids)
        keyset = set((str(a), str(b)) for (a, b) in keys)
        self.tablew.model.remove_where(
            lambda row: (str(row.get("layer_id", "")), str(row.get("feature_id", "")))
            in keyset
        )
        # Also delete from plot
        self.plot_widget.delete_selected()
        
        self.tablew.clear_selection()
        self._clear_all_map_selections()

    def _clear_vector(self) -> None:
        self.vector.clear()
        self.tablew.remove_where(
            lambda r: str(r.get("layer_id", "")) == str(self.vector.id)
        )
        self.mapw.set_vector_selection(self.vector.id, [])
        self.tablew.clear_selection()

    def _clear_fast_points(self) -> None:
        self.fast.clear()
        self.tablew.remove_where(
            lambda r: str(r.get("layer_id", "")) == str(self.fast.id)
        )
        self.mapw.set_fast_points_selection(self.fast.id, [])
        self.tablew.clear_selection()

    def _clear_fast_geo(self) -> None:
        self.fast_geo.clear()
        self.tablew.remove_where(
            lambda r: str(r.get("layer_id", "")) == str(self.fast_geo.id)
        )
        self.tablew.clear_selection()
        # Clear map-side selection too (keeps map/table in sync).
        try:
            self.mapw.set_fast_geopoints_selection(self.fast_geo.id, [])
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def _clear_all_map_selections(self) -> None:
        self.mapw.set_vector_selection(self.vector.id, [])
        self.mapw.set_fast_points_selection(self.fast.id, [])
        self.mapw.set_fast_geopoints_selection(self.fast_geo.id, [])

    # ---- selection sync ----
    def _on_map_selection(self, sel) -> None:
        layer_id = getattr(sel, "layer_id", "")
        fids = list(getattr(sel, "feature_ids", []) or [])
        if not layer_id:
            return
        if not fids:
            return
        keys = [(layer_id, str(fid)) for fid in fids]
        self.tablew.select_keys(keys, clear_first=True)
        self.plot_widget.select_keys(keys, clear_first=True)

    def _on_table_selection_changed(self, keys) -> None:
        by_layer: Dict[str, List[str]] = {}
        for layer_id, fid in keys or []:
            by_layer.setdefault(str(layer_id), []).append(str(fid))
        if not by_layer:
            self._clear_all_map_selections()
            self.plot_widget.clear_selection()
            return
        for layer_id, fids in by_layer.items():
            if layer_id == str(self.vector.id):
                self.mapw.set_vector_selection(self.vector.id, fids)
            elif layer_id == str(self.fast.id):
                self.mapw.set_fast_points_selection(self.fast.id, fids)
            elif layer_id == str(self.fast_geo.id):
                self.mapw.set_fast_geopoints_selection(self.fast_geo.id, fids)
        self.plot_widget.select_keys(keys, clear_first=True)

    def _on_plot_selection(self, keys) -> None:
        """Handle selection from plot widget."""
        if not keys:
            return
        by_layer: Dict[str, List[str]] = {}
        for layer_id, fid in keys:
            by_layer.setdefault(str(layer_id), []).append(str(fid))
        
        # Update map selection
        for layer_id, fids in by_layer.items():
            if layer_id == str(self.vector.id):
                self.mapw.set_vector_selection(self.vector.id, fids)
            elif layer_id == str(self.fast.id):
                self.mapw.set_fast_points_selection(self.fast.id, fids)
            elif layer_id == str(self.fast_geo.id):
                self.mapw.set_fast_geopoints_selection(self.fast_geo.id, fids)
        
        # Update table selection
        self.tablew.select_keys(keys, clear_first=True)
        for layer_id, fid in keys or []:
            by_layer.setdefault(str(layer_id), []).append(str(fid))
        if not by_layer:
            self._clear_all_map_selections()
            return
        for layer_id, fids in by_layer.items():
            if layer_id == str(self.vector.id):
                self.mapw.set_vector_selection(self.vector.id, fids)
            elif layer_id == str(self.fast.id):
                self.mapw.set_fast_points_selection(self.fast.id, fids)
            elif layer_id == str(self.fast_geo.id):
                self.mapw.set_fast_geopoints_selection(self.fast_geo.id, fids)


def main() -> None:
    """Run the pyopenlayersqt demo application."""
    app = QtWidgets.QApplication(sys.argv)
    w = ShowcaseWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
