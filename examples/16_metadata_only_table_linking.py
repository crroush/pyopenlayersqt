#!/usr/bin/env python3
"""Fast-geo parent table linked to metadata-only child rows.

This example demonstrates the complementary workflow where parent features
exist on the map (100k FastGeo points), and each parent maps to multiple
metadata-only child rows (3-5 rows per parent, no child map objects).
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView

from pyopenlayersqt import FastGeoPointsStyle, OLMapWidget
from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget
from pyopenlayersqt.selection_linking import MultiSelectLink, TableLink


class MetadataOnlyChildLinkingExample(QtWidgets.QMainWindow):
    """Demonstrate FastGeo parent features linked to metadata-only child rows."""

    TOTAL_PARENT_POINTS = 100_000
    MIN_META_PER_PARENT = 3
    MAX_META_PER_PARENT = 5

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Dual Table Linking: 100k FastGeo parent + metadata child")
        self.resize(1750, 940)

        self.map_widget = OLMapWidget(center=(39.8, -98.6), zoom=4)

        self.parent_layer = self.map_widget.add_fast_geopoints_layer(
            "parent_geos",
            selectable=True,
            style=FastGeoPointsStyle(
                point_radius=2.5,
                default_color=QColor("deepskyblue"),
                selected_point_radius=5.5,
                selected_color=QColor("yellow"),
                ellipse_stroke_color=QColor("orange"),
                selected_ellipse_stroke_color=QColor("cyan"),
                fill_ellipses=False,
                min_ellipse_px=2.0,
            ),
        )

        self.parents_table = self._create_parent_table()
        self.metadata_table = self._create_metadata_table(self.parent_layer.id)
        self.parents_table.table.setSelectionMode(QAbstractItemView.ExtendedSelection)

        self.parent_ids: list[str] = []
        self.parent_by_meta: dict[str, str] = {}
        self._benchmark = (
            os.environ.get("PYOPENLAYERSQT_BENCH", "") == "1"
            or os.environ.get("PYOPENLAYERSQT_PERF", "") == "1"
        )

        self.link = MultiSelectLink(
            map_widget=self.map_widget,
            parent=TableLink(table=self.parents_table, layer=self.parent_layer),
            kids={
                "metadata": TableLink(
                    table=self.metadata_table,
                    key_layer_id=self.parent_layer.id,
                )
            },
            parent_by_kid={"metadata": self.parent_by_meta},
            clear_parent_on_kid_subset=True,
        )

        self.map_widget.ready.connect(self._add_data)

        self._build_layout()

    def _perf_log(self, message: str) -> None:
        if self._benchmark:
            print(f"[PERF] {message}")

    def _create_parent_table(self) -> FeatureTableWidget:
        columns = [
            ColumnSpec("Geo ID", lambda r: r.get("feature_id", "")),
            ColumnSpec("Region", lambda r: r.get("region", "")),
            ColumnSpec("Lat", lambda r: r.get("lat", "")),
            ColumnSpec("Lon", lambda r: r.get("lon", "")),
            ColumnSpec("Meta Rows", lambda r: r.get("meta_count", "")),
        ]
        return FeatureTableWidget(
            columns=columns,
            key_fn=lambda r: (str(r.get("layer_id")), str(r.get("feature_id"))),
            sorting_enabled=True,
        )

    def _create_metadata_table(self, layer_id: str) -> FeatureTableWidget:
        columns = [
            ColumnSpec("Meta ID", lambda r: r.get("feature_id", "")),
            ColumnSpec("Geo ID", lambda r: r.get("geo_id", "")),
            ColumnSpec("Type", lambda r: r.get("record_type", "")),
            ColumnSpec("Status", lambda r: r.get("status", "")),
            ColumnSpec("Score", lambda r: r.get("score", "")),
            ColumnSpec("Owner", lambda r: r.get("owner", "")),
        ]
        return FeatureTableWidget(
            columns=columns,
            key_fn=lambda r: (layer_id, str(r.get("feature_id"))),
            sorting_enabled=True,
        )

    def _build_layout(self) -> None:
        info = QtWidgets.QLabel(
            "<b>Workflow:</b> Table 1 is 100k FastGeo map objects. "
            "Table 2 is metadata-only with 3-5 rows per geo (no map features). "
            "Selecting parent geos fans out selection to their metadata rows."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "background-color: #e8f4f8; padding: 8px; border-radius: 4px;"
        )

        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self.parents_table, "Table 1: Parent geos (100k)")
        tabs.addTab(self.metadata_table, "Table 2: Metadata rows (no map geometry)")

        vertical_split = QtWidgets.QSplitter(Qt.Vertical)
        vertical_split.addWidget(self.map_widget)
        vertical_split.addWidget(tabs)
        vertical_split.setStretchFactor(0, 4)
        vertical_split.setStretchFactor(1, 2)

        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(info)
        layout.addWidget(vertical_split, stretch=1)

        self.setCentralWidget(container)

    def _add_data(self) -> None:
        t0 = time.perf_counter()
        rng = np.random.default_rng(17)

        parent_seed = [
            ("West", 34.05, -118.24),
            ("Mountain", 39.74, -104.99),
            ("Midwest", 41.88, -87.63),
            ("East", 40.71, -74.00),
            ("Pacific NW", 47.61, -122.33),
            ("Southwest", 33.45, -112.07),
            ("Plains", 39.10, -94.58),
            ("Southeast", 33.75, -84.39),
            ("Northeast", 42.36, -71.06),
            ("South", 29.76, -95.36),
        ]

        parent_rows: list[dict[str, str]] = []
        metadata_rows: list[dict[str, str]] = []

        base_count = self.TOTAL_PARENT_POINTS // len(parent_seed)
        remainder = self.TOTAL_PARENT_POINTS % len(parent_seed)

        global_idx = 0
        for idx, (region, lat, lon) in enumerate(parent_seed):
            local_count = base_count + (1 if idx < remainder else 0)

            offsets_lat = (rng.random(local_count) - 0.5) * 2.1
            offsets_lon = (rng.random(local_count) - 0.5) * 2.5
            coords = [
                (lat + float(offsets_lat[i]), lon + float(offsets_lon[i]))
                for i in range(local_count)
            ]

            sma_m = rng.uniform(20.0, 180.0, size=local_count).tolist()
            smi_m = rng.uniform(10.0, 120.0, size=local_count).tolist()
            tilt_deg = rng.uniform(0.0, 180.0, size=local_count).tolist()

            ids = [f"geo_{global_idx + i}" for i in range(local_count)]
            self.parent_layer.add_points_with_ellipses(
                coords=coords,
                sma_m=sma_m,
                smi_m=smi_m,
                tilt_deg=tilt_deg,
                ids=ids,
            )

            for i, geo_id in enumerate(ids):
                meta_count = int(
                    rng.integers(self.MIN_META_PER_PARENT, self.MAX_META_PER_PARENT + 1)
                )
                self.parent_ids.append(geo_id)
                parent_rows.append(
                    {
                        "region": region,
                        "lat": f"{coords[i][0]:.5f}",
                        "lon": f"{coords[i][1]:.5f}",
                        "meta_count": str(meta_count),
                        "layer_id": self.parent_layer.id,
                        "feature_id": geo_id,
                    }
                )

                for j in range(meta_count):
                    meta_id = f"meta_{geo_id}_{j}"
                    self.parent_by_meta[meta_id] = geo_id
                    metadata_rows.append(
                        {
                            "feature_id": meta_id,
                            "geo_id": geo_id,
                            "record_type": ["inspection", "permit", "ticket", "asset"][
                                j % 4
                            ],
                            "status": ["open", "in_progress", "closed"][(idx + j) % 3],
                            "score": str(int(rng.integers(50, 100))),
                            "owner": f"Team {(idx % 6) + 1}",
                        }
                    )

            global_idx += local_count

        self.parents_table.append_rows(parent_rows)
        self.metadata_table.append_rows(metadata_rows)
        self.link.set_links({"metadata": self.parent_by_meta})

        # Start with a small selected subset to show fan-out in metadata table.
        self.link.set_parent(self.parent_ids[:5])

        dt = time.perf_counter() - t0
        self._perf_log(
            f"data load complete: {len(self.parent_ids):,} parent geos"
            f", {len(metadata_rows):,} metadata rows in {dt:.2f} s"
        )


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = MetadataOnlyChildLinkingExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
