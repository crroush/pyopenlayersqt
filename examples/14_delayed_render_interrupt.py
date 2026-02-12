#!/usr/bin/env python3
"""Delayed raster rendering with debounce + hard interrupt.

Key ideas demonstrated:
- Fixed geographic polygon footprint (does not change with zoom).
- Raster resolution derived from current viewport pixel size.
- Expensive render executed in a child process.
- In-flight render interrupted when a newer request arrives.
- Clear UI feedback showing when recompute happens and at what resolution.
"""

import io
import math
import multiprocessing as mp
import sys
import time
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw
from PySide6 import QtCore, QtWidgets

from pyopenlayersqt import OLMapWidget, RasterStyle

def _haversine_m(lat1, lon1, lat2, lon2):
    r = 6_371_000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _polygon_bounds_latlon(polygon_latlon):
    lats = [lat for lat, _ in polygon_latlon]
    lons = [lon for _, lon in polygon_latlon]
    return (min(lats), min(lons)), (max(lats), max(lons))


def _polygon_latlon_to_pixel_polygon(polygon_latlon, width, height, bounds):
    """Map a lat/lon polygon to pixel coordinates within raster bounds."""
    (lat_min, lon_min), (lat_max, lon_max) = bounds
    lon_span = max(1e-12, lon_max - lon_min)
    lat_span = max(1e-12, lat_max - lat_min)

    points = []
    for lat, lon in polygon_latlon:
        x = (lon - lon_min) / lon_span * (width - 1)
        y = (lat_max - lat) / lat_span * (height - 1)
        points.append((x, y))
    return points


def _fixed_heat_value(lon, lat):
    """Deterministic heat field over geography (fixed function in world coords)."""
    # coordinates around SF Bay (~[-122.6,-122.3], [37.65,37.9])
    x = (lon + 122.45) * 70.0
    y = (lat - 37.77) * 70.0

    # Smooth base structure + medium/high frequency texture
    v = (
        0.45 * np.exp(-((x + 2.0) ** 2 + (y - 1.5) ** 2) / 8.0)
        + 0.35 * np.exp(-((x - 1.0) ** 2 + (y + 2.2) ** 2) / 5.5)
        + 0.20 * np.sin(2.3 * x) * np.cos(1.9 * y)
        + 0.10 * np.sin(7.0 * x + 1.2 * y)
        + 0.08 * np.cos(6.3 * y - 1.5 * x)
    )
    return v


@dataclass
class RenderRequest:
    request_id: int
    polygon_latlon: list[tuple[float, float]]
    raster_bounds: tuple[tuple[float, float], tuple[float, float]]
    width_px: int
    height_px: int
    quality: int
    q_lon: float
    q_lat: float


def _generate_expensive_masked_heatmap(request: RenderRequest):
    """Generate expensive PNG for a fixed geographic heatmap sampled at given resolution."""
    width = request.width_px
    height = request.height_px

    # Simulate heavy non-cooperative native compute.
    rng = np.random.default_rng(10_000 + width + height + request.quality)
    matrix_n = max(220, 180 + request.quality * 100)
    heavy = rng.normal(size=(matrix_n, matrix_n)).astype(np.float32)
    _ = heavy @ heavy.T

    (lat_min, lon_min), (lat_max, lon_max) = request.raster_bounds
    lon_axis = np.linspace(lon_min, lon_max, width, dtype=np.float32)
    lat_axis = np.linspace(lat_max, lat_min, height, dtype=np.float32)
    lon_grid, lat_grid = np.meshgrid(lon_axis, lat_axis)

    # Quantize geo coordinates based on current view pixel size so low zoom is
    # intentionally coarser, and zoom-in reveals finer structure.
    q_lon = max(1e-12, float(request.q_lon))
    q_lat = max(1e-12, float(request.q_lat))
    lon_q = np.round(lon_grid / q_lon) * q_lon
    lat_q = np.round(lat_grid / q_lat) * q_lat

    # Fixed world-space field (same phenomenon every time), sampled at
    # quantized coords to make resolution change visually obvious.
    field = _fixed_heat_value(lon_q, lat_q)

    # Add tiny deterministic "sensor texture" to make detail gain visible at high res.
    field += 0.02 * np.sin(lon_grid * 180.0) * np.cos(lat_grid * 220.0)

    # Normalize
    vmin = float(field.min())
    vmax = float(field.max())
    if vmax > vmin:
        field = (field - vmin) / (vmax - vmin)

    colors = np.array(
        [
            [68, 1, 84, 255],
            [59, 82, 139, 255],
            [33, 145, 140, 255],
            [94, 201, 98, 255],
            [253, 231, 37, 255],
        ],
        dtype=np.uint8,
    )
    idx = np.clip((field * (len(colors) - 1)).astype(np.int32), 0, len(colors) - 1)
    rgba = colors[idx]

    img = Image.fromarray(rgba, mode="RGBA")

    # Mask to fixed polygon.
    mask = Image.new("L", (width, height), 0)
    draw_mask = ImageDraw.Draw(mask)
    polygon_px = _polygon_latlon_to_pixel_polygon(
        request.polygon_latlon, width, height, request.raster_bounds
    )
    draw_mask.polygon(polygon_px, fill=255)
    img.putalpha(mask)

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _render_worker(request: RenderRequest, out_queue):
    try:
        t0 = time.perf_counter()
        png = _generate_expensive_masked_heatmap(request)
        elapsed = time.perf_counter() - t0
        out_queue.put(
            {
                "request_id": request.request_id,
                "png": png,
                "bounds": request.raster_bounds,
                "elapsed_s": elapsed,
                "width_px": request.width_px,
                "height_px": request.height_px,
                "quality": request.quality,
                "q_lon": request.q_lon,
                "q_lat": request.q_lat,
            }
        )
    except Exception as exc:
        out_queue.put({"request_id": request.request_id, "error": str(exc)})


class DelayedRenderInterruptExample(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Delayed Raster Render with Debounce + Interrupt")
        self.resize(1200, 860)

        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=10)

        self.polygon_latlon = [
            (37.700, -122.545),
            (37.735, -122.515),
            (37.800, -122.500),
            (37.845, -122.465),
            (37.842, -122.410),
            (37.815, -122.365),
            (37.770, -122.340),
            (37.725, -122.360),
            (37.695, -122.420),
            (37.682, -122.490),
        ]
        self.polygon_bounds = _polygon_bounds_latlon(self.polygon_latlon)
        (pb_lat_min, pb_lon_min), (pb_lat_max, pb_lon_max) = self.polygon_bounds
        pb_lat_mid = (pb_lat_min + pb_lat_max) * 0.5
        pb_lon_mid = (pb_lon_min + pb_lon_max) * 0.5
        self._polygon_width_m = _haversine_m(pb_lat_mid, pb_lon_min, pb_lat_mid, pb_lon_max)
        self._polygon_height_m = _haversine_m(pb_lat_min, pb_lon_mid, pb_lat_max, pb_lon_mid)

        self.raster_layer = None
        self._watch_handle = None
        self._latest_extent = None
        self._next_request_id = 0
        self._active_request_id = -1
        self._active_process = None
        self._result_queue = None
        self._interrupt_count = 0
        self._ctx = mp.get_context("spawn")
        self._last_render_key = None

        self._debounce_timer = QtCore.QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._start_render_for_latest_extent)

        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self._poll_results)

        controls = self._create_controls()
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(controls)
        layout.addWidget(self.map_widget, stretch=1)
        self.setCentralWidget(container)

        self.map_widget.ready.connect(self._on_map_ready)

    def closeEvent(self, event):
        self._stop_current_process()
        if self._watch_handle is not None:
            self._watch_handle.cancel()
            self._watch_handle = None
        super().closeEvent(event)

    def _create_controls(self):
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(panel)

        info = QtWidgets.QLabel(
            "Fixed geographic heatmap footprint. Zooming changes computed raster "
            "pixel dimensions (shown in status + image stamp)."
        )
        info.setWordWrap(True)
        layout.addWidget(info, stretch=3)

        compute_box = QtWidgets.QGroupBox("Compute")
        compute_layout = QtWidgets.QHBoxLayout(compute_box)
        compute_layout.addWidget(QtWidgets.QLabel("Quality:"))
        self.quality_spin = QtWidgets.QSpinBox()
        self.quality_spin.setRange(1, 5)
        self.quality_spin.setValue(3)
        self.quality_spin.valueChanged.connect(self._schedule_render)
        compute_layout.addWidget(self.quality_spin)
        layout.addWidget(compute_box, stretch=1)

        self.status_label = QtWidgets.QLabel("Waiting for first extent...")
        self.status_label.setMinimumWidth(640)
        layout.addWidget(self.status_label, stretch=3)

        return panel

    def _on_map_ready(self):
        self._watch_handle = self.map_widget.watch_view_extent(
            self._on_view_extent,
            debounce_ms=250,
        )

    def _on_view_extent(self, extent):
        self._latest_extent = extent
        self._schedule_render()

    def _schedule_render(self):
        if self._latest_extent is None:
            return
        self._debounce_timer.start(220)

    def _start_render_for_latest_extent(self):
        if self._latest_extent is None:
            return

        ext = self._latest_extent

        view_width_px = max(1.0, float(ext.get("width_px", 1024.0)))
        view_height_px = max(1.0, float(ext.get("height_px", 768.0)))
        resolution_m_per_px = max(1e-9, float(ext.get("resolution", 1.0)))

        # Use view resolution so panning (same zoom/resolution) does not change target.
        width_px = int(np.clip(self._polygon_width_m / resolution_m_per_px, 180, 1600))
        height_px = int(np.clip(self._polygon_height_m / resolution_m_per_px, 180, 1600))

        # Quantization follows view resolution; higher zoom -> smaller bins -> sharper.
        # Approximate deg/px at polygon centroid latitude.
        (lat_min, lon_min), (lat_max, lon_max) = self.polygon_bounds
        centroid_lat = (lat_min + lat_max) * 0.5
        meters_per_deg_lon = max(1.0, 111_320.0 * np.cos(np.radians(centroid_lat)))
        meters_per_deg_lat = 110_540.0
        q_lon = max(1e-12, (resolution_m_per_px * 6.0) / meters_per_deg_lon)
        q_lat = max(1e-12, (resolution_m_per_px * 6.0) / meters_per_deg_lat)

        # Pan should not force recompute if effective sampling/resolution is unchanged.
        render_key = (
            int(width_px),
            int(height_px),
            round(resolution_m_per_px, 6),
            int(view_width_px),
            int(view_height_px),
            int(self.quality_spin.value()),
        )
        if render_key == self._last_render_key:
            self.status_label.setText(
                f"⏸ skipped (pan/no resolution change) | raster={width_px}x{height_px}px "
                f"| res≈{resolution_m_per_px:.3f} m/px | bin≈{q_lon:.6f}°, {q_lat:.6f}° | interrupts={self._interrupt_count}"
            )
            return
        self._last_render_key = render_key

        self._next_request_id += 1
        request_id = self._next_request_id
        self._active_request_id = request_id

        request = RenderRequest(
            request_id=request_id,
            polygon_latlon=self.polygon_latlon,
            raster_bounds=self.polygon_bounds,
            width_px=width_px,
            height_px=height_px,
            quality=int(self.quality_spin.value()),
            q_lon=q_lon,
            q_lat=q_lat,
        )

        if self._active_process is not None and self._active_process.is_alive():
            self._active_process.terminate()
            self._active_process.join(timeout=0.2)
            self._interrupt_count += 1

        self._result_queue = self._ctx.Queue()
        self._active_process = self._ctx.Process(
            target=_render_worker,
            args=(request, self._result_queue),
            daemon=True,
        )
        self._active_process.start()
        self._poll_timer.start()

        self.status_label.setText(
            f"⏳ recomputing req#{request_id} | target={width_px}x{height_px}px "
            f"| view={int(view_width_px)}x{int(view_height_px)}px "
            f"| res≈{resolution_m_per_px:.3f} m/px | bin≈{q_lon:.6f}°, {q_lat:.6f}° | interrupts={self._interrupt_count}"
        )

    def _poll_results(self):
        if self._result_queue is None:
            return

        got_message = False
        while not self._result_queue.empty():
            got_message = True
            msg = self._result_queue.get()
            if int(msg.get("request_id", -1)) != self._active_request_id:
                continue

            if "error" in msg:
                self.status_label.setText(
                    f"❌ render #{self._active_request_id} failed: {msg['error']}"
                )
                self._poll_timer.stop()
                return

            if self.raster_layer is not None:
                self.raster_layer.remove()

            self.raster_layer = self.map_widget.add_raster_image(
                msg["png"],
                bounds=[tuple(msg["bounds"][0]), tuple(msg["bounds"][1])],
                style=RasterStyle(opacity=0.74),
                name=f"dynamic_heatmap_{self._active_request_id}",
            )

            elapsed = float(msg.get("elapsed_s", 0.0))
            self.status_label.setText(
                f"✅ updated req#{self._active_request_id} in {elapsed:.2f}s "
                f"| raster={msg.get('width_px')}x{msg.get('height_px')}px "
                f"| quality={msg.get('quality')} "
                f"| bin≈{float(msg.get('q_lon', 0.0)):.6f}°, {float(msg.get('q_lat', 0.0)):.6f}° "
                f"| interrupts={self._interrupt_count}"
            )
            self._poll_timer.stop()
            return

        if (
            not got_message
            and self._active_process is not None
            and not self._active_process.is_alive()
        ):
            self._poll_timer.stop()

    def _stop_current_process(self):
        if self._poll_timer.isActive():
            self._poll_timer.stop()
        if self._active_process is not None:
            if self._active_process.is_alive():
                self._active_process.terminate()
            self._active_process.join(timeout=0.5)
            self._active_process = None


def main():
    mp.freeze_support()
    app = QtWidgets.QApplication(sys.argv)
    window = DelayedRenderInterruptExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
