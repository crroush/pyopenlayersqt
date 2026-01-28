#!/usr/bin/env python3
"""Two tables + one map selection benchmark (with highlight channels).

Use case:
  - One map with a fast geo-points layer (N points)
  - Two feature tables in tabs:
      * Geo table: one row per geo feature
      * Meta table: 2-5 rows per geo feature (40k-50k+ rows typical)

Rules:
  - Selecting in the GEO table updates:
      * map selection (geo layer)
      * META table highlight (channel="geo")
  - Selecting on the MAP updates:
      * GEO table selection
      * META table highlight (channel="geo")
  - Selecting in the META table does NOT affect geo table or map.
    (Meta table is highlight-only; selection is disabled.)

This example records timing stats for selection propagation and shows them
in the GUI, while printing brief updates to the console.

Run:
  python examples/07_two_tables_selection_benchmark.py --n-geo 10000
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from PySide6 import QtCore, QtWidgets

from pyopenlayersqt import (
    ColumnSpec,
    FeatureTableWidget,
    FastGeoPointsLayer,
    FastGeoPointsStyle,
    OLMapWidget,
)


FeatureKey = Tuple[str, str]


@dataclass
class TimingAgg:
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    def add(self, ms: float) -> None:
        self.count += 1
        self.total_ms += ms
        self.max_ms = max(self.max_ms, ms)

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count else 0.0


class PerfStats:
    def __init__(self) -> None:
        self._aggs: Dict[str, TimingAgg] = {}

    def add_timing(self, name: str, ms: float) -> None:
        self._aggs.setdefault(name, TimingAgg()).add(ms)

    def snapshot(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for k, a in sorted(self._aggs.items()):
            out[k] = f"avg={a.avg_ms:.2f}ms max={a.max_ms:.2f}ms n={a.count}"
        return out


class BenchWindow(QtWidgets.QMainWindow):
    def __init__(self, *, n_geo: int) -> None:
        super().__init__()
        self.setWindowTitle("pyopenlayersqt - selection benchmark")

        self._n_geo = int(n_geo)
        self.stats = PerfStats()

        # Guards to prevent selection feedback loops
        self._ignore_map_events = False
        self._ignore_geo_events = False

        # geo_id (str) -> meta row ranges (inclusive)
        self.geo_to_meta_ranges: Dict[str, List[Tuple[int, int]]] = {}

        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        self.map_widget = OLMapWidget(self)
        layout.addWidget(self.map_widget, 3)

        self.tabs = QtWidgets.QTabWidget(self)
        layout.addWidget(self.tabs, 2)

        self.perf_label = QtWidgets.QLabel(self)
        self.perf_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        layout.addWidget(self.perf_label, 0)

        # Geo table (master selection)
        self.geo_table = FeatureTableWidget(
            columns=[
                ColumnSpec("Geo ID", lambda r: r.get("geo_id", "")),
                ColumnSpec("Lat", lambda r: f"{r.get('lat', 0.0):.5f}"),
                ColumnSpec("Lon", lambda r: f"{r.get('lon', 0.0):.5f}"),
                ColumnSpec("Meta links", lambda r: str(r.get("n_meta", 0))),
            ],
            key_fn=lambda r: (str(r.get("layer_id")), str(r.get("feature_id"))),
        )

        # Meta table (highlight-only, selection disabled)
        self.meta_table = FeatureTableWidget(
            columns=[
                ColumnSpec("Meta ID", lambda r: r.get("meta_id", "")),
                ColumnSpec("Geo ID", lambda r: r.get("geo_id", "")),
                ColumnSpec("Kind", lambda r: r.get("kind", "")),
            ],
            key_fn=lambda r: ("meta", str(r.get("meta_id"))),
            sorting_enabled=True,
            selection_enabled=False,
        )

        self.tabs.addTab(self.geo_table, "Geo table")
        self.tabs.addTab(self.meta_table, "Meta table")

        # Connect signals
        self.geo_table.selectionKeysChanged.connect(self._on_geo_table_selection)
        self.map_widget.selectionChanged.connect(self._on_map_selection)

        # Populate once JS is ready
        self.map_widget.ready.connect(self._populate)

    def _populate(self) -> None:
        rng = np.random.default_rng(0)
        n = self._n_geo

        lats = 32 + rng.random(n) * 10
        lons = -125 + rng.random(n) * 10
        ids = [str(i) for i in range(n)]

        # Create geo layer
        self.geo_layer = self.map_widget.add_fast_geopoints_layer(
            name="geo",
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
            show_ellipses=False,
        )
        coords = [(float(lats[i]), float(lons[i])) for i in range(n)]
        sma = [0.0] * n
        smi = [0.0] * n
        tilt = [0.0] * n
        self.geo_layer.add_points_with_ellipses(
            coords=coords,
            sma_m=sma,
            smi_m=smi,
            tilt_deg=tilt,
            ids=ids,
        )

        # Geo table rows
        geo_rows = []
        for i in range(n):
            geo_rows.append(
                {
                    "layer_id": self.geo_layer.id,
                    "feature_id": ids[i],
                    "geo_id": ids[i],
                    "lat": float(lats[i]),
                    "lon": float(lons[i]),
                    "n_meta": int(rng.integers(2, 6)),
                }
            )
        self.geo_table.append_rows(geo_rows)

        # Meta table rows (grouped by geo_id so each geo maps to contiguous ranges)
        meta_rows = []
        kinds = ["A", "B", "C", "D", "E"]
        meta_id = 0
        self.geo_to_meta_ranges.clear()

        for i in range(n):
            gid = ids[i]
            k = int(geo_rows[i]["n_meta"])
            start = len(meta_rows)
            for _ in range(k):
                mid = f"m{meta_id}"
                meta_id += 1
                meta_rows.append(
                    {
                        "meta_id": mid,
                        "geo_id": gid,
                        "kind": kinds[int(rng.integers(0, len(kinds)))],
                    }
                )
            if k > 0:
                end = len(meta_rows) - 1
                self.geo_to_meta_ranges[gid] = [(start, end)]
            else:
                self.geo_to_meta_ranges[gid] = []

        self.meta_table.append_rows(meta_rows)

        print(
            f"Populated {len(geo_rows)} geo rows and {len(meta_rows)} meta rows "
            f"(avg meta/geo ≈ {len(meta_rows)/max(1,len(geo_rows)):.2f})."
        )

    def _update_perf_ui(self, prefix: str) -> None:
        snap = self.stats.snapshot()
        lines = [f"{k}: {v}" for k, v in snap.items() if k.startswith(prefix)]
        self.perf_label.setText("\n".join(lines))

    def _apply_meta_highlight_from_geo_ids(self, geo_ids: List[str]) -> None:
        # For large/sortable meta tables we highlight by row value (geo_id column),
        # which stays correct under sorting and avoids expensive QItemSelection work.
        t0 = time.perf_counter()
        geo_set = set(str(g) for g in geo_ids)
        self.stats.add_timing("link.meta_value_set", (time.perf_counter() - t0) * 1000.0)

        t0 = time.perf_counter()
        if geo_set:
            # meta table column 1 is geo_id in this example
            self.meta_table.set_highlighted_values("geo", column=1, values=geo_set)
        else:
            self.meta_table.clear_highlight("geo")
        self.stats.add_timing("link.meta_highlight_apply", (time.perf_counter() - t0) * 1000.0)

    @QtCore.Slot(list)
    def _on_geo_table_selection(self, keys: List[FeatureKey]) -> None:
        if self._ignore_geo_events:
            return

        t0_total = time.perf_counter()

        # Extract selected geo ids
        t0 = time.perf_counter()
        geo_ids = [fid for (layer_id, fid) in keys if layer_id == self.geo_layer.id]
        self.stats.add_timing("geo_sel.extract_geo_ids", (time.perf_counter() - t0) * 1000.0)

        # Update meta highlight (always)
        self._apply_meta_highlight_from_geo_ids(geo_ids)

        # Update map selection unless selection originated from map
        if not self._ignore_map_events:
            t0 = time.perf_counter()
            self.map_widget.set_fast_geopoints_selection(self.geo_layer.id, list(geo_ids))
            self.stats.add_timing("geo_sel.map_set_selected", (time.perf_counter() - t0) * 1000.0)

        self.stats.add_timing("geo_sel.total", (time.perf_counter() - t0_total) * 1000.0)
        self._update_perf_ui("geo_sel")
        # Print a compact line occasionally
        if self.stats._aggs.get("geo_sel.total", TimingAgg()).count % 10 == 1:
            print("PERF:", {"geo_sel.total": self.stats.snapshot().get("geo_sel.total")})

    @QtCore.Slot(object)
    def _on_map_selection(self, selection) -> None:
        # Only react to geo layer selection events
        if selection is None:
            return
        if getattr(selection, "layer_id", None) != self.geo_layer.id:
            return
        if self._ignore_map_events:
            return

        geo_ids = [str(x) for x in (getattr(selection, "feature_ids", []) or [])]

        # Map -> Geo table (selection) -> Meta highlight
        self._ignore_map_events = True
        self._ignore_geo_events = True
        try:
            if geo_ids:
                keys = [(self.geo_layer.id, gid) for gid in geo_ids]
                self.geo_table.select_keys(keys, clear_first=True)
            else:
                self.geo_table.clear_selection()
        finally:
            self._ignore_geo_events = False
            self._ignore_map_events = False

        # Apply meta highlight directly for map-driven change (avoid relying on geo signal)
        self._apply_meta_highlight_from_geo_ids(geo_ids)
        self._update_perf_ui("link")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-geo", type=int, default=10000, help="Number of geo points / rows")
    args = parser.parse_args(argv)

    app = QtWidgets.QApplication(sys.argv)

    w = BenchWindow(n_geo=args.n_geo)
    w.resize(1200, 850)
    w.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
