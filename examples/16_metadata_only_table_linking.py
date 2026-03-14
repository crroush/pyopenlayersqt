#!/usr/bin/env python3
"""Region geometry linked to metadata-only child rows.

This example demonstrates the complementary workflow where parent features
exist on the map, but child records are metadata-only (no map objects).
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

from pyopenlayersqt import OLMapWidget, PointStyle
from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget
from pyopenlayersqt.selection_linking import MultiSelectLink, TableLink


class MetadataOnlyChildLinkingExample(QtWidgets.QMainWindow):
    """Demonstrate region geometry linked to metadata-only child rows."""

    SITES_PER_REGION = 10_000

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Dual Table Linking: Region Geometry + Site Metadata")
        self.resize(1700, 920)

        self.map_widget = OLMapWidget(center=(39.8, -98.6), zoom=4)

        self.region_layer = self.map_widget.add_vector_layer("regions", selectable=True)
        self.regions_table = self._create_regions_table()
        self.sites_table = self._create_sites_table(self.region_layer.id)
        self.regions_table.table.setSelectionMode(QAbstractItemView.ExtendedSelection)

        self.region_ids: list[str] = []
        self.region_by_site: dict[str, str] = {}
        self._benchmark = (
            os.environ.get("PYOPENLAYERSQT_BENCH", "") == "1"
            or os.environ.get("PYOPENLAYERSQT_PERF", "") == "1"
        )

        self.link = MultiSelectLink(
            map_widget=self.map_widget,
            parent=TableLink(table=self.regions_table, layer=self.region_layer),
            kids={
                "sites": TableLink(
                    table=self.sites_table,
                    key_layer_id=self.region_layer.id,
                )
            },
            parent_by_kid={"sites": self.region_by_site},
            clear_parent_on_kid_subset=True,
        )

        self.map_widget.ready.connect(self._add_data)

        self._build_layout()

    def _perf_log(self, message: str) -> None:
        if self._benchmark:
            print(f"[PERF] {message}")

    def _create_regions_table(self) -> FeatureTableWidget:
        columns = [
            ColumnSpec("Region", lambda r: r.get("name", "")),
            ColumnSpec("Region ID", lambda r: r.get("feature_id", "")),
            ColumnSpec("Category", lambda r: r.get("category", "")),
            ColumnSpec("Sites", lambda r: r.get("site_count", "")),
        ]
        return FeatureTableWidget(
            columns=columns,
            key_fn=lambda r: (str(r.get("layer_id")), str(r.get("feature_id"))),
            sorting_enabled=True,
        )

    def _create_sites_table(self, layer_id: str) -> FeatureTableWidget:
        columns = [
            ColumnSpec("Site", lambda r: r.get("site_name", "")),
            ColumnSpec("Site ID", lambda r: r.get("feature_id", "")),
            ColumnSpec("Region", lambda r: r.get("region_name", "")),
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
            "<b>Workflow:</b> Table 1 is backed by map geometries (regions). "
            "Table 2 is metadata-only (no map features). Selecting region(s) in Table 1 "
            "selects the mapped metadata rows in Table 2."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "background-color: #e8f4f8; padding: 8px; border-radius: 4px;"
        )

        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self.regions_table, "Table 1: Regions (multi-select)")
        tabs.addTab(self.sites_table, "Table 2: Site metadata (no map geometry)")

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
        rng = np.random.default_rng(7)

        region_seed = [
            ("West", "Operations", 34.05, -118.24),
            ("Mountain", "Logistics", 39.74, -104.99),
            ("Midwest", "Manufacturing", 41.88, -87.63),
            ("East", "Sales", 40.71, -74.00),
            ("Pacific NW", "Research", 47.61, -122.33),
            ("Southwest", "Field", 33.45, -112.07),
            ("Plains", "Supply", 39.10, -94.58),
            ("Southeast", "Support", 33.75, -84.39),
            ("Northeast", "Product", 42.36, -71.06),
            ("South", "Delivery", 29.76, -95.36),
        ]

        site_rows = []

        for idx, (name, category, lat, lon) in enumerate(region_seed):
            region_id = f"region_{idx}"
            self.region_ids.append(region_id)

            self.region_layer.add_points(
                [(lat, lon)],
                ids=[region_id],
                style=PointStyle(
                    radius=12.0,
                    fill_color=QColor("crimson"),
                    stroke_color=QColor("darkred"),
                    stroke_width=2.0,
                ),
            )
            self.regions_table.append_rows(
                [
                    {
                        "name": name,
                        "category": category,
                        "site_count": f"{self.SITES_PER_REGION:,}",
                        "layer_id": self.region_layer.id,
                        "feature_id": region_id,
                    }
                ]
            )

            count = self.SITES_PER_REGION
            site_ids = [f"site_{idx}_{i}" for i in range(count)]
            scores = rng.integers(50, 100, size=count)

            for i, site_id in enumerate(site_ids):
                self.region_by_site[site_id] = region_id
                site_rows.append(
                    {
                        "site_name": f"{name} Site {i + 1}",
                        "region_name": name,
                        "score": str(scores[i]),
                        "feature_id": site_id,
                        "owner": f"Team {(idx % 5) + 1}",
                    }
                )

        self.sites_table.append_rows(site_rows)
        self.link.set_links({"sites": self.region_by_site})

        self.link.set_parent([self.region_ids[0]])

        if self._benchmark:
            dt = time.perf_counter() - t0
            total_sites = self.SITES_PER_REGION * len(region_seed)
            self._perf_log(
                f"data load complete: {len(region_seed)} regions"
                f", {total_sites:,} sites in {dt:.2f} s"
            )


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = MetadataOnlyChildLinkingExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
