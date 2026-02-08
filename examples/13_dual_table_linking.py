#!/usr/bin/env python3
"""Dual-table map integration with multi-region + high-volume child features.

This example extends the table integration pattern by using two tables in tabs below the map:
- Table 1 (multi-select): parent features (regions)
- Table 2 (multi-select): all child features (sites) across regions

Selection works in both directions:
- Table 1 <-> parent layer on the map
- Table 2 <-> child layer on the map
- Selecting child features on the map promotes/highlights owning regions in Table 1.

Dataset scale:
- 10 regions
- 100,000 total site points (10,000 per region)
"""

from __future__ import annotations

import os
import sys
import time

import numpy as np
from PySide6 import QtWidgets
from PySide6.QtCore import QSignalBlocker, Qt
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

        self.region_layer = self.map_widget.add_vector_layer("regions", selectable=True)
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
        self.regions_table.table.setSelectionMode(QAbstractItemView.ExtendedSelection)

        self.region_ids: list[str] = []
        self.site_by_region: dict[str, list[str]] = {}
        self.region_by_site: dict[str, str] = {}
        self._selected_region_ids: set[str] = set()
        self._selected_site_ids: set[str] = set()
        self._benchmark = (
            os.environ.get("PYOPENLAYERSQT_BENCH", "") == "1"
            or os.environ.get("PYOPENLAYERSQT_PERF", "") == "1"
        )

        self.map_widget.selectionChanged.connect(self._on_map_selection)
        self.regions_table.selectionKeysChanged.connect(self._on_region_table_selection)
        self.sites_table.selectionKeysChanged.connect(self._on_site_table_selection)
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
            "<b>Workflow:</b> Selecting region(s) in Table 1 selects all corresponding sites "
            "in Table 2 and on the map. If you draw a subset selection on the map, only Table 2 "
            "is highlighted and Table 1 is cleared."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "background-color: #e8f4f8; padding: 8px; border-radius: 4px;"
        )

        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self.regions_table, "Table 1: Regions (multi-select)")
        tabs.addTab(self.sites_table, "Table 2: Sites (all visible, multi-select)")

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
            offsets_lat = (rng.random(count) - 0.5) * 2.2
            offsets_lon = (rng.random(count) - 0.5) * 2.6
            coords = [
                (lat + offsets_lat[i], lon + offsets_lon[i]) for i in range(count)
            ]

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

        # Start with one selected region, selecting all corresponding sites.
        self._apply_region_selection([self.region_ids[0]])

        if self._benchmark:
            dt = time.perf_counter() - t0
            total_sites = self.SITES_PER_REGION * len(region_seed)
            perf_str = (
                f"data load complete: {len(region_seed)} regions"
                f", {total_sites:,} sites in {dt:.2f} s"
            )

            self._perf_log(perf_str)

    def _apply_region_selection(
        self,
        region_ids: list[str],
        *,
        update_map_selection: bool = True,
    ) -> None:
        t0 = time.perf_counter()
        selected = list(dict.fromkeys(region_ids))
        self._selected_region_ids = set(selected)

        self.regions_table.select_keys(
            [(self.region_layer.id, rid) for rid in selected],
            clear_first=True,
        )
        if update_map_selection:
            self.map_widget.set_vector_selection(self.region_layer.id, selected)

        # Region selection means select all sites for those region(s).
        selected_site_ids = [
            sid for rid in selected for sid in self.site_by_region.get(rid, [])
        ]
        self._selected_site_ids = set(selected_site_ids)
        self.sites_table.select_keys(
            [(self.site_layer.id, sid) for sid in selected_site_ids],
            clear_first=True,
        )
        # This site-layer selection is programmatic (driven by region table/map region),
        # not a user subset action on the site layer.
        self._set_site_map_selection_programmatically(selected_site_ids)

        if self._benchmark:
            dt = (time.perf_counter() - t0) * 1000.0
            self._perf_log(
                f"region selection -> {len(selected)} regions, "
                f"{len(selected_site_ids):,} sites selected in {dt:.1f} ms"
            )

    def _on_region_table_selection(self, keys: list[tuple[str, str]]) -> None:
        if self._syncing_from_map:
            return
        region_ids = [fid for _layer_id, fid in keys]
        self._apply_region_selection(region_ids)

    def _on_site_table_selection(self, keys: list[tuple[str, str]]) -> None:
        if self._syncing_from_map:
            return

        site_ids = [fid for _layer_id, fid in keys]
        t0 = time.perf_counter()
        self._selected_site_ids = set(site_ids)
        # Programmatic write to map from table should not be interpreted as a user
        # map-subset gesture that clears region selection.
        self._set_site_map_selection_programmatically(site_ids)

        if self._benchmark:
            dt = (time.perf_counter() - t0) * 1000.0
            self._perf_log(
                f"site table -> map selection ({len(site_ids):,} ids) in {dt:.1f} ms"
            )

    def _expected_site_ids_for_selected_regions(self) -> set[str]:
        """Return the full site-id union implied by current region selection."""
        return {
            sid
            for rid in self._selected_region_ids
            for sid in self.site_by_region.get(rid, [])
        }

    def _on_map_selection(self, selection) -> None:
        self._syncing_from_map = True
        try:
            if selection.layer_id == self.region_layer.id:
                region_ids = list(selection.feature_ids)
                self._apply_region_selection(region_ids, update_map_selection=False)
                return

            if selection.layer_id == self.site_layer.id:
                site_ids = list(selection.feature_ids)
                incoming_site_ids = set(site_ids)

                # If incoming site selection exactly matches the currently selected
                # region union, treat this as synchronization echo and do not clear
                # parent region selection.
                expected_site_ids = self._expected_site_ids_for_selected_regions()
                if self._selected_region_ids and incoming_site_ids == expected_site_ids:
                    self._selected_site_ids = incoming_site_ids
                    return

                self._selected_site_ids = incoming_site_ids

                # Map subset selection highlights sites only; clear region table/map selection.
                self._selected_region_ids.clear()
                self.regions_table.clear_selection()
                self.map_widget.set_vector_selection(self.region_layer.id, [])

                self.sites_table.select_keys(
                    [(self.site_layer.id, sid) for sid in site_ids],
                    clear_first=True,
                )
                if self._benchmark:
                    self._perf_log(
                        f"map -> site table selection ({len(site_ids):,} ids), regions cleared"
                    )
        finally:
            self._syncing_from_map = False

    def _set_site_map_selection_programmatically(self, site_ids: list[str]) -> None:
        """Write site selection to map without emitting selectionChanged callbacks."""
        blocker = QSignalBlocker(self.map_widget)
        self.map_widget.set_fast_points_selection(self.site_layer.id, site_ids)
        del blocker


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = DualTableLinkingExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
