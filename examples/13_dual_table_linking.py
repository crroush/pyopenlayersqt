#!/usr/bin/env python3
"""Dual-table map integration with multi-region + high-volume child features.

This example extends the table integration pattern by using two tables in tabs below the map:
- Table 1 (multi-select): parent features (regions)
- Table 2 (multi-select): child features (sites) belonging to selected regions

Selection works in both directions:
- Table 1 <-> parent layer on the map
- Table 2 <-> child layer on the map
- Selecting child features on the map also promotes/selects owning regions in Table 1.

Dataset scale:
- 10 regions
- 100,000 total site points (10,000 per region)
"""

from __future__ import annotations

import sys

import numpy as np
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView

from pyopenlayersqt import FastPointsStyle, OLMapWidget, PointStyle
from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget


class DualTableLinkingExample(QtWidgets.QMainWindow):
    """Demonstrate linked parent/child selection across two tables and map layers."""

    SITES_PER_REGION = 10_000

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Dual Table Linking: Multi-Region + 100k Sites")
        self.resize(1700, 920)

        self._syncing_from_map = False

        self.map_widget = OLMapWidget(center=(39.8, -98.6), zoom=4)

        # Table 1 / Layer 1: regions (multi-select)
        self.region_layer = self.map_widget.add_vector_layer("regions", selectable=True)

        # Table 2 / Layer 2: sites (multi-select)
        self.site_layer = self.map_widget.add_fast_points_layer(
            "sites",
            selectable=True,
            style=FastPointsStyle(
                radius=3.0,
                default_color=QColor("dodgerblue"),
                selected_radius=6.0,
                selected_color=QColor("yellow"),
            ),
        )

        self.regions_table = self._create_regions_table()
        self.sites_table = self._create_sites_table()

        # Parent table is now multi-select as requested.
        self.regions_table.table.setSelectionMode(QAbstractItemView.ExtendedSelection)

        self.region_ids: list[str] = []
        self.site_by_region: dict[str, list[str]] = {}
        self.region_by_site: dict[str, str] = {}
        self._all_site_keys: list[tuple[str, str]] = []
        self._selected_region_ids: set[str] = set()

        self.map_widget.selectionChanged.connect(self._on_map_selection)
        self.regions_table.selectionKeysChanged.connect(self._on_region_table_selection)
        self.sites_table.selectionKeysChanged.connect(self._on_site_table_selection)
        self.map_widget.ready.connect(self._add_data)

        self._build_layout()

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

    def _create_sites_table(self) -> FeatureTableWidget:
        columns = [
            ColumnSpec("Site", lambda r: r.get("site_name", "")),
            ColumnSpec("Site ID", lambda r: r.get("feature_id", "")),
            ColumnSpec("Region", lambda r: r.get("region_name", "")),
            ColumnSpec("Score", lambda r: r.get("score", "")),
        ]
        return FeatureTableWidget(
            columns=columns,
            key_fn=lambda r: (str(r.get("layer_id")), str(r.get("feature_id"))),
            sorting_enabled=True,
        )

    def _build_layout(self) -> None:
        info = QtWidgets.QLabel(
            "<b>Workflow:</b> Use tabs below the map. Multi-select regions in Table 1 "
            "(or on-map red markers), then multi-select sites in Table 2. "
            "This demo loads 100,000 site points to show large-scale synchronization."
        )
        info.setWordWrap(True)
        info.setStyleSheet("background-color: #e8f4f8; padding: 8px; border-radius: 4px;")

        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self.regions_table, "Table 1: Regions (multi-select)")
        tabs.addTab(self.sites_table, "Table 2: Sites (multi-select)")

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
            self.regions_table.append_rows([
                {
                    "name": name,
                    "category": category,
                    "site_count": f"{self.SITES_PER_REGION:,}",
                    "layer_id": self.region_layer.id,
                    "feature_id": region_id,
                }
            ])

            count = self.SITES_PER_REGION
            offsets_lat = (rng.random(count) - 0.5) * 2.2
            offsets_lon = (rng.random(count) - 0.5) * 2.6
            coords = [(lat + offsets_lat[i], lon + offsets_lon[i]) for i in range(count)]

            site_ids = [f"site_{idx}_{i}" for i in range(count)]
            self.site_layer.add_points(coords, ids=site_ids)

            self.site_by_region[region_id] = list(site_ids)
            scores = rng.integers(50, 100, size=count)
            for i, site_id in enumerate(site_ids):
                self.region_by_site[site_id] = region_id
                site_rows.append(
                    {
                        "site_name": f"{name} Site {i + 1}",
                        "region_name": name,
                        "score": str(scores[i]),
                        "layer_id": self.site_layer.id,
                        "feature_id": site_id,
                    }
                )

        self.sites_table.append_rows(site_rows)
        self._all_site_keys = [(self.site_layer.id, row["feature_id"]) for row in site_rows]

        # Start with two selected regions to demonstrate multi-select behavior.
        self._apply_region_selection(self.region_ids[:2])

    def _apply_region_selection(
        self,
        region_ids: list[str],
        *,
        update_map_selection: bool = True,
    ) -> None:
        selected = list(dict.fromkeys(region_ids))
        self._selected_region_ids = set(selected)

        self.regions_table.select_keys(
            [(self.region_layer.id, rid) for rid in selected],
            clear_first=True,
        )
        if update_map_selection:
            self.map_widget.set_vector_selection(self.region_layer.id, selected)

        if not selected:
            # With no selected region, keep child table empty/cleared.
            self.sites_table.show_all_rows()
            self.sites_table.hide_rows_by_keys(self._all_site_keys)
            self.sites_table.clear_selection()
            self.map_widget.set_fast_points_selection(self.site_layer.id, [])
            return

        allowed_ids = {
            site_id
            for rid in selected
            for site_id in self.site_by_region.get(rid, [])
        }
        hide_keys = [k for k in self._all_site_keys if k[1] not in allowed_ids]

        self.sites_table.show_all_rows()
        if hide_keys:
            self.sites_table.hide_rows_by_keys(hide_keys)

        # Drop any child selection now out of scope.
        selected_site_ids = [
            fid for _layer_id, fid in self.sites_table.selected_keys() if fid in allowed_ids
        ]
        self.sites_table.select_keys(
            [(self.site_layer.id, sid) for sid in selected_site_ids],
            clear_first=True,
        )
        self.map_widget.set_fast_points_selection(self.site_layer.id, selected_site_ids)

    def _on_region_table_selection(self, keys: list[tuple[str, str]]) -> None:
        if self._syncing_from_map:
            return
        region_ids = [fid for _layer_id, fid in keys]
        self._apply_region_selection(region_ids)

    def _on_site_table_selection(self, keys: list[tuple[str, str]]) -> None:
        if self._syncing_from_map:
            return

        site_ids = [fid for _layer_id, fid in keys]
        if self._selected_region_ids:
            allowed = {
                sid
                for rid in self._selected_region_ids
                for sid in self.site_by_region.get(rid, [])
            }
            site_ids = [fid for fid in site_ids if fid in allowed]

        self.map_widget.set_fast_points_selection(self.site_layer.id, site_ids)

    def _on_map_selection(self, selection) -> None:
        self._syncing_from_map = True
        try:
            if selection.layer_id == self.region_layer.id:
                region_ids = list(selection.feature_ids)
                self._apply_region_selection(region_ids, update_map_selection=False)
                return

            if selection.layer_id == self.site_layer.id:
                site_ids = list(selection.feature_ids)

                if site_ids:
                    owners = {
                        self.region_by_site[sid]
                        for sid in site_ids
                        if sid in self.region_by_site
                    }
                    if owners and owners != self._selected_region_ids:
                        self._apply_region_selection(
                            sorted(owners),
                            update_map_selection=False,
                        )
                    allowed = {
                        sid
                        for rid in self._selected_region_ids
                        for sid in self.site_by_region.get(rid, [])
                    }
                    site_ids = [sid for sid in site_ids if sid in allowed]

                self.sites_table.select_keys(
                    [(self.site_layer.id, sid) for sid in site_ids],
                    clear_first=True,
                )
        finally:
            self._syncing_from_map = False


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = DualTableLinkingExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
