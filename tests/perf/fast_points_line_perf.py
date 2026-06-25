#!/usr/bin/env python3
"""FastPoints 200K line performance probe.

This is an intentionally small manual test application for investigating where
large FastPoints payloads and render requests stall. It generates points along a
single latitude span (default: 0 to 10 degrees at longitude 0) and enables the
PYOPENLAYERSQT_PERF logging path so both Python and JavaScript timings are
printed to stdout.

Run from the repository root, for example:

    PYOPENLAYERSQT_PERF=1 python tests/perf/fast_points_line_perf.py --points 200000

By default this sends all generated points in one FastPoints payload so the
probe matches the observed 200K-point workflow rather than measuring chunked
loading behavior.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtWidgets
from PySide6.QtGui import QColor

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pyopenlayersqt import FastPointsStyle, OLMapWidget


def perf(message: str, **fields: object) -> None:
    """Emit a consistently formatted manual PERF line."""
    suffix = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"PERF: app {message}" + (f" {suffix}" if suffix else ""), flush=True)


def build_points(point_count: int, lat_min: float, lat_max: float, lon: float):
    start = time.perf_counter()
    lats = np.linspace(lat_min, lat_max, point_count, dtype=np.float64)
    lons = np.full(point_count, lon, dtype=np.float64)
    coords = list(zip(lats.tolist(), lons.tolist()))
    ids = [f"line_{i}" for i in range(point_count)]
    perf(
        "generated_inputs",
        points=point_count,
        elapsed_ms=round((time.perf_counter() - start) * 1000.0, 2),
    )
    return coords, ids


class FastPointsLinePerfApp(QtWidgets.QWidget):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__()
        self.args = args
        self.setWindowTitle("FastPoints 200K Line PERF Probe")

        self.map_widget = OLMapWidget(
            center=((args.lat_min + args.lat_max) / 2.0, args.lon),
            zoom=args.zoom,
            show_osm_layer=not args.no_osm,
            show_country_boundaries=False,
        )
        self.map_widget.perfReceived.connect(self._on_perf)
        self.map_widget.ready.connect(self._on_ready)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.map_widget)
        self.resize(args.width, args.height)

    @QtCore.Slot()
    def _on_ready(self) -> None:
        perf("map_ready")
        QtCore.QTimer.singleShot(0, self._load_points)

    @QtCore.Slot(dict)
    def _on_perf(self, payload: dict) -> None:
        perf("bridge_event", payload=payload)

    def _load_points(self) -> None:
        total_start = time.perf_counter()
        coords, ids = build_points(
            self.args.points,
            self.args.lat_min,
            self.args.lat_max,
            self.args.lon,
        )

        layer_start = time.perf_counter()
        layer = self.map_widget.add_fast_points_layer(
            "200k_line_fast_points",
            selectable=False,
            style=FastPointsStyle(
                radius=self.args.radius,
                default_color=QColor(self.args.color),
                selected_radius=self.args.radius,
                selected_color=QColor(self.args.color),
            ),
            cell_size_m=self.args.cell_size_m,
        )
        perf(
            "add_layer_returned",
            elapsed_ms=round((time.perf_counter() - layer_start) * 1000.0, 2),
        )

        add_start = time.perf_counter()
        chunk_size = self.args.chunk_size or self.args.points
        layer.add_points(coords, ids=ids, chunk_size=chunk_size)
        perf(
            "add_points_returned",
            points=self.args.points,
            chunk_size=chunk_size,
            elapsed_ms=round((time.perf_counter() - add_start) * 1000.0, 2),
        )
        perf(
            "load_sequence_returned",
            elapsed_ms=round((time.perf_counter() - total_start) * 1000.0, 2),
        )

        self.map_widget.fit_bounds(
            [(self.args.lat_min, self.args.lon), (self.args.lat_max, self.args.lon)]
        )
        perf("fit_bounds_requested")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points", type=int, default=200_000)
    parser.add_argument("--lat-min", type=float, default=0.0)
    parser.add_argument("--lat-max", type=float, default=10.0)
    parser.add_argument("--lon", type=float, default=0.0)
    parser.add_argument("--zoom", type=int, default=5)
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=None,
        help="FastPoints add_points chunk size; defaults to --points for one payload.",
    )
    parser.add_argument("--cell-size-m", type=float, default=750.0)
    parser.add_argument("--radius", type=float, default=2.0)
    parser.add_argument("--color", default="#00aa00")
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--no-osm", action="store_true")
    return parser.parse_args()


def main() -> int:
    os.environ.setdefault("PYOPENLAYERSQT_PERF", "1")
    args = parse_args()
    app = QtWidgets.QApplication(sys.argv)
    window = FastPointsLinePerfApp(args)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
