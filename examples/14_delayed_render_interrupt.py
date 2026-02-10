#!/usr/bin/env python3
"""Delayed raster rendering with debounce + hard interrupt.

This example builds on ``05_raster_overlay.py`` and demonstrates a pattern for
expensive, zoom-dependent heatmap rendering that keeps the GUI responsive:

- Uses ``watch_view_extent(..., debounce_ms=...)`` to avoid recomputing for every
  tiny navigation event.
- Starts heavy computation in a separate process (not the Qt event thread).
- Interrupts in-flight work with ``Process.terminate()`` when a new extent
  arrives (last-request-wins, no queue buildup).
- Raster pixel dimensions are derived from current map extent resolution.
- Heatmap is masked by an arbitrary polygon shape.

Why process-based interruption?
    In real systems, expensive work is often a single blocking C++/pybind11 call.
    A thread cannot preempt that call safely. A child process can be terminated.
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
    """Great-circle distance in meters between two lon/lat points."""
    r = 6_371_000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class RenderRequest:
    request_id: int
    bounds: tuple[tuple[float, float], tuple[float, float]]  # ((lat_min, lon_min), (lat_max, lon_max))
    width_px: int
    height_px: int
    quality: int


def _make_arbitrary_polygon(width, height):
    """Create an arbitrary polygon in pixel coordinates."""
    shape_pct = [
        (0.10, 0.56),
        (0.16, 0.28),
        (0.35, 0.10),
        (0.57, 0.18),
        (0.82, 0.12),
        (0.94, 0.37),
        (0.82, 0.68),
        (0.64, 0.90),
        (0.40, 0.84),
        (0.18, 0.76),
    ]
    return [(x * width, y * height) for x, y in shape_pct]


def _generate_expensive_masked_heatmap(width, height, quality):
    """Generate a computationally expensive masked heatmap PNG bytes."""
    rng = np.random.default_rng(1000 + width + height + quality)

    # Simulate a heavy, effectively uninterruptible call (e.g., pybind11/C++):
    # expensive dense linear algebra in one block.
    matrix_n = max(250, 220 + quality * 90)
    heavy = rng.normal(size=(matrix_n, matrix_n)).astype(np.float32)
    _ = heavy @ heavy.T

    # Heatmap via inverse-distance accumulation from random sources.
    n_points = 160 + quality * 80
    point_x = rng.random(n_points) * width
    point_y = rng.random(n_points) * height
    point_values = rng.random(n_points)

    x = np.arange(width, dtype=np.float32)
    y = np.arange(height, dtype=np.float32)
    grid_x, grid_y = np.meshgrid(x, y)

    grid_values = np.zeros((height, width), dtype=np.float32)
    for i in range(n_points):
        dx = grid_x - point_x[i]
        dy = grid_y - point_y[i]
        dist = np.sqrt(dx * dx + dy * dy)
        dist = np.maximum(dist, 1.0)
        grid_values += point_values[i] / (dist + 14.0)

    grid_min = float(grid_values.min())
    grid_max = float(grid_values.max())
    if grid_max > grid_min:
        grid_values = (grid_values - grid_min) / (grid_max - grid_min)

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

    indices = (grid_values * (len(colors) - 1)).astype(np.int32)
    indices = np.clip(indices, 0, len(colors) - 1)
    rgba = colors[indices]

    img = Image.fromarray(rgba, mode="RGBA")

    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.polygon(_make_arbitrary_polygon(width, height), fill=255)
    img.putalpha(mask)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _render_worker(request: RenderRequest, out_queue):
    """Child-process entry point."""
    try:
        t0 = time.perf_counter()
        png = _generate_expensive_masked_heatmap(
            request.width_px,
            request.height_px,
            request.quality,
        )
        elapsed = time.perf_counter() - t0
        out_queue.put(
            {
                "request_id": request.request_id,
                "png": png,
                "bounds": request.bounds,
                "elapsed_s": elapsed,
                "width_px": request.width_px,
                "height_px": request.height_px,
            }
        )
    except Exception as exc:
        out_queue.put({"request_id": request.request_id, "error": str(exc)})


class DelayedRenderInterruptExample(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Delayed Raster Render with Debounce + Interrupt")
        self.resize(1200, 840)

        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=10)

        self.raster_layer = None
        self._watch_handle = None
        self._latest_extent = None
        self._next_request_id = 0
        self._active_request_id = -1
        self._active_process = None
        self._result_queue = None
        self._interrupt_count = 0
        self._ctx = mp.get_context("spawn")

        self._debounce_timer = QtCore.QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._start_render_for_latest_extent)

        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(60)
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
            "Zoom or pan the map. A debounced extent watcher triggers expensive "
            "heatmap recomputation in a child process. In-flight jobs are "
            "terminated on new requests so UI remains responsive."
        )
        info.setWordWrap(True)
        layout.addWidget(info, stretch=3)

        quality_box = QtWidgets.QGroupBox("Compute Load")
        quality_layout = QtWidgets.QHBoxLayout(quality_box)
        quality_layout.addWidget(QtWidgets.QLabel("Quality:"))
        self.quality_spin = QtWidgets.QSpinBox()
        self.quality_spin.setRange(1, 5)
        self.quality_spin.setValue(3)
        self.quality_spin.valueChanged.connect(self._schedule_render)
        quality_layout.addWidget(self.quality_spin)
        layout.addWidget(quality_box, stretch=1)

        self.status_label = QtWidgets.QLabel("Waiting for first extent...")
        self.status_label.setMinimumWidth(420)
        layout.addWidget(self.status_label, stretch=2)

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
        lon_min = float(ext["lon_min"])
        lat_min = float(ext["lat_min"])
        lon_max = float(ext["lon_max"])
        lat_max = float(ext["lat_max"])
        resolution_m_per_px = max(1e-3, float(ext.get("resolution", 100.0)))

        mid_lat = (lat_min + lat_max) / 2.0
        mid_lon = (lon_min + lon_max) / 2.0
        extent_width_m = _haversine_m(mid_lat, lon_min, mid_lat, lon_max)
        extent_height_m = _haversine_m(lat_min, mid_lon, lat_max, mid_lon)

        width_px = int(np.clip(extent_width_m / resolution_m_per_px, 220, 1100))
        height_px = int(np.clip(extent_height_m / resolution_m_per_px, 220, 1100))

        self._next_request_id += 1
        request_id = self._next_request_id
        self._active_request_id = request_id

        request = RenderRequest(
            request_id=request_id,
            bounds=((lat_min, lon_min), (lat_max, lon_max)),
            width_px=width_px,
            height_px=height_px,
            quality=int(self.quality_spin.value()),
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
            f"Rendering request #{request_id} at {width_px}x{height_px} px "
            f"(interrupts={self._interrupt_count})..."
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
                    f"Render #{self._active_request_id} failed: {msg['error']}"
                )
                self._poll_timer.stop()
                return

            if self.raster_layer is not None:
                self.raster_layer.remove()

            self.raster_layer = self.map_widget.add_raster_image(
                msg["png"],
                bounds=[tuple(msg["bounds"][0]), tuple(msg["bounds"][1])],
                style=RasterStyle(opacity=0.72),
                name=f"dynamic_heatmap_{self._active_request_id}",
            )

            elapsed = float(msg.get("elapsed_s", 0.0))
            self.status_label.setText(
                f"Rendered #{self._active_request_id} in {elapsed:.2f}s at "
                f"{msg.get('width_px')}x{msg.get('height_px')} px "
                f"(interrupts={self._interrupt_count})."
            )
            self._poll_timer.stop()
            return

        if not got_message and self._active_process is not None and not self._active_process.is_alive():
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
