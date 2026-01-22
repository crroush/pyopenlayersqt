#!/usr/bin/env python3
"""Simple validation script to ensure small datasets still work correctly.

This script verifies that:
1. Small datasets (<1000 points) render correctly
2. Selection works at various zoom levels
3. No regressions in basic functionality
"""

from __future__ import annotations

import sys
import numpy as np
from PySide6 import QtWidgets

from pyopenlayersqt import (
    FastPointsStyle,
    FastGeoPointsStyle,
    OLMapWidget,
)


class SmallDatasetTest(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Small Dataset Validation")
        self.resize(800, 600)
        
        # Create map centered on US
        self.map_widget = OLMapWidget(center=(39.0, -98.0), zoom=4)
        self.setCentralWidget(self.map_widget)
        
        # Connect to ready signal
        self.map_widget.ready.connect(self._on_map_ready)
        self.map_widget.selectionChanged.connect(self._on_selection)
        
    def _on_map_ready(self):
        """Add small test datasets."""
        print("Map ready, adding test data...")
        
        # Test 1: Small FastPoints layer (100 points)
        rng = np.random.default_rng(seed=123)
        n = 100
        lats = 30 + rng.random(n) * 15
        lons = -125 + rng.random(n) * 30
        coords = list(zip(lats.tolist(), lons.tolist()))
        
        fast = self.map_widget.add_fast_points_layer(
            "small_fast",
            selectable=True,
            style=FastPointsStyle(
                radius=4.0,
                default_rgba=(255, 100, 100, 200),
                selected_radius=8.0,
                selected_rgba=(255, 255, 0, 255)
            )
        )
        fast.add_points(coords, ids=[f"pt{i}" for i in range(n)])
        print(f"✓ Added {n} FastPoints")
        
        # Test 2: Small FastGeoPoints layer (50 points with ellipses)
        n2 = 50
        lats2 = 35 + rng.random(n2) * 10
        lons2 = -110 + rng.random(n2) * 20
        coords2 = list(zip(lats2.tolist(), lons2.tolist()))
        sma = (100 + rng.random(n2) * 400).tolist()
        smi = (50 + rng.random(n2) * 200).tolist()
        tilt = (rng.random(n2) * 360).tolist()
        
        geo = self.map_widget.add_fast_geopoints_layer(
            "small_geo",
            selectable=True,
            style=FastGeoPointsStyle(
                point_radius=4.0,
                default_point_rgba=(100, 100, 255, 200),
                selected_point_radius=8.0,
                selected_point_rgba=(255, 255, 255, 255),
                ellipse_stroke_rgba=(100, 100, 255, 150),
                ellipses_visible=True
            )
        )
        geo.add_points_with_ellipses(
            coords=coords2,
            sma_m=sma,
            smi_m=smi,
            tilt_deg=tilt,
            ids=[f"geo{i}" for i in range(n2)]
        )
        print(f"✓ Added {n2} FastGeoPoints with ellipses")
        
        print("\nValidation tests:")
        print("1. Points should be visible and render correctly")
        print("2. Try clicking on points to select them")
        print("3. Try drag-selecting multiple points")
        print("4. Zoom in/out - all points should remain visible")
        print("5. Selection should work at all zoom levels")
        print("\n✓ Small dataset validation ready")
        
    def _on_selection(self, selection):
        """Log selections."""
        count = len(selection.feature_ids) if selection.feature_ids else 0
        if count > 0:
            print(f"Selection: {selection.layer_id}, {count} points")


def main():
    app = QtWidgets.QApplication(sys.argv)
    
    window = SmallDatasetTest()
    window.show()
    
    print("\n" + "="*60)
    print("SMALL DATASET VALIDATION")
    print("="*60)
    print("\nThis test ensures small datasets work correctly.")
    print("All points should render and be selectable.")
    print("="*60 + "\n")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
