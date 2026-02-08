#!/usr/bin/env python3
"""Dual-table map integration with parent/child selection flow.

This example extends the table integration pattern by using two tables:
- Table 1 (single-select): parent features (regions)
- Table 2 (multi-select): child features (sites) belonging to the selected region

Selection works in both directions:
- Table 1 <-> parent layer on the map
- Table 2 <-> child layer on the map
- Clicking a child feature on the map also updates Table 1 to the owning parent.
"""

from __future__ import annotations

import sys

import numpy as np
from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView

from pyopenlayersqt import OLMapWidget, FastPointsStyle, PointStyle
from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget


class DualTableLinkingExample(QtWidgets.QMainWindow):
    """Demonstrate linked parent/child selection across two tables and map layers."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Dual Table Linking: Parent/Child + Map Selection")
        self.resize(1700, 900)

        self._syncing_from_map = False

        self.map_widget = OLMapWidget(center=(39.8, -98.6), zoom=4)

        # Table 1 / Layer 1: regions (single-select)
        self.region_layer = self.map_widget.add_vector_layer("regions", selectable=True)

        # Table 2 / Layer 2: sites (multi-select)
        self.site_layer = self.map_widget.add_fast_points_layer(
            "sites",
            selectable=True,
            style=FastPointsStyle(
                radius=4.0,
                default_color=QColor("dodgerblue"),
                selected_radius=7.0,
                selected_color=QColor("yellow"),
            ),
        )

        self.regions_table = self._create_regions_table()
        self.sites_table = self._create_sites_table()

        # Make parent table explicitly single-select.
        self.regions_table.table.setSelectionMode(QAbstractItemView.SingleSelection)

        self.region_ids: list[str] = []
        self.site_by_region: dict[str, list[str]] = {}
        self.region_by_site: dict[str, str] = {}
        self._all_site_keys: list[tuple[str, str]] = []
        self._active_region_id: str | None = None

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
            "<b>Workflow:</b> Use the tabs below the map. Select one region in Table 1 "
            "(or on the map), then multi-select its sites in Table 2. Selections stay synchronized "
            "across both tables and both layers."
        )
        info.setWordWrap(True)
        info.setStyleSheet("background-color: #e8f4f8; padding: 8px; border-radius: 4px;")

        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self.regions_table, "Table 1: Regions (single-select)")
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
                    "layer_id": self.region_layer.id,
                    "feature_id": region_id,
                }
            ])

            count = 8
            offsets_lat = (rng.random(count) - 0.5) * 2.2
            offsets_lon = (rng.random(count) - 0.5) * 2.6
            coords = [(lat + offsets_lat[i], lon + offsets_lon[i]) for i in range(count)]

            site_ids = [f"site_{idx}_{i}" for i in range(count)]
            self.site_layer.add_points(coords, ids=site_ids)

            self.site_by_region[region_id] = list(site_ids)
            for i, site_id in enumerate(site_ids):
                self.region_by_site[site_id] = region_id
                site_rows.append(
                    {
                        "site_name": f"{name} Site {i + 1}",
                        "region_name": name,
                        "score": f"{50 + int(rng.random() * 50)}",
                        "layer_id": self.site_layer.id,
                        "feature_id": site_id,
                    }
                )

        self.sites_table.append_rows(site_rows)
        self._all_site_keys = [
            (self.site_layer.id, row["feature_id"])
            for row in site_rows
        ]

        # Start with first region selected.
        self._set_active_region(self.region_ids[0])

    def _set_active_region(
        self,
        region_id: str,
        *,
        update_map_selection: bool = True,
    ) -> None:
        self._active_region_id = region_id

        self.regions_table.select_keys([(self.region_layer.id, region_id)], clear_first=True)
        if update_map_selection:
            self.map_widget.set_vector_selection(self.region_layer.id, [region_id])

        allowed_ids = set(self.site_by_region.get(region_id, []))
        hide_keys = [k for k in self._all_site_keys if k[1] not in allowed_ids]

        self.sites_table.show_all_rows()
        if hide_keys:
            self.sites_table.hide_rows_by_keys(hide_keys)

        self.sites_table.clear_selection()
        self.map_widget.set_fast_points_selection(self.site_layer.id, [])

    def _on_region_table_selection(self, keys: list[tuple[str, str]]) -> None:
        if self._syncing_from_map or not keys:
            return
        _, region_id = keys[0]
        self._set_active_region(region_id)

    def _on_site_table_selection(self, keys: list[tuple[str, str]]) -> None:
        if self._syncing_from_map:
            return

        site_ids = [fid for _layer_id, fid in keys]
        if self._active_region_id:
            allowed = set(self.site_by_region.get(self._active_region_id, []))
            site_ids = [fid for fid in site_ids if fid in allowed]

        self.map_widget.set_fast_points_selection(self.site_layer.id, site_ids)

    def _on_map_selection(self, selection) -> None:
        self._syncing_from_map = True
        try:
            if selection.layer_id == self.region_layer.id:
                if selection.feature_ids:
                    region_id = selection.feature_ids[0]
                    self._set_active_region(region_id, update_map_selection=False)
                else:
                    self.regions_table.clear_selection()
                    self._active_region_id = None
                    self.sites_table.show_all_rows()
                    self.sites_table.clear_selection()
                    self.map_widget.set_fast_points_selection(self.site_layer.id, [])
                return

            if selection.layer_id == self.site_layer.id:
                site_ids = list(selection.feature_ids)

                if site_ids:
                    owner = self.region_by_site.get(site_ids[0])
                    if owner and owner != self._active_region_id:
                        self._set_active_region(owner, update_map_selection=False)
                    allowed = set(self.site_by_region.get(self._active_region_id or "", []))
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
