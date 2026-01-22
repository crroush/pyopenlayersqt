#!/usr/bin/env python3
"""Test script to validate performance improvements for large point rendering.

This script creates a map with 100k points and tests:
1. Rendering performance at different zoom levels
2. Selection behavior (click and drag-select)
3. Interaction performance (pan/zoom)
"""

from __future__ import annotations

import sys
import time
from typing import List, Tuple

import numpy as np
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt, QTimer

from pyopenlayersqt import (
    FastPointsStyle,
    FastGeoPointsStyle,
    OLMapWidget,
)


class PerformanceTestWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Large Point Rendering Performance Test")
        self.resize(1400, 900)
        
        # Create main widget with controls and map
        main_widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(main_widget)
        
        # Control panel
        control_panel = self._create_control_panel()
        layout.addWidget(control_panel, 0)
        
        # Map widget - start at world view
        self.map_widget = OLMapWidget(center=(0.0, 0.0), zoom=2)
        layout.addWidget(self.map_widget, 1)
        
        self.setCentralWidget(main_widget)
        
        # Connect to map ready signal
        self.map_widget.ready.connect(self._on_map_ready)
        
        # Track performance metrics from JS
        self.map_widget.jsEvent.connect(self._on_js_event)
        
        # State
        self.fast_layer = None
        self.fast_geo_layer = None
        self.perf_data = []
        self.last_selection = None
        
    def _create_control_panel(self) -> QtWidgets.QWidget:
        """Create control panel with test controls."""
        panel = QtWidgets.QWidget()
        panel.setMaximumWidth(350)
        layout = QtWidgets.QVBoxLayout(panel)
        
        # Title
        title = QtWidgets.QLabel("Performance Test Controls")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Point count selector
        count_group = QtWidgets.QGroupBox("Point Count")
        count_layout = QtWidgets.QVBoxLayout(count_group)
        
        self.count_spin = QtWidgets.QSpinBox()
        self.count_spin.setRange(1000, 500000)
        self.count_spin.setSingleStep(10000)
        self.count_spin.setValue(100000)
        count_layout.addWidget(QtWidgets.QLabel("Number of points:"))
        count_layout.addWidget(self.count_spin)
        
        layout.addWidget(count_group)
        
        # Layer selection
        layer_group = QtWidgets.QGroupBox("Layer Type")
        layer_layout = QtWidgets.QVBoxLayout(layer_group)
        
        self.layer_combo = QtWidgets.QComboBox()
        self.layer_combo.addItems(["FastPoints", "FastGeoPoints", "Both"])
        layer_layout.addWidget(self.layer_combo)
        
        layout.addWidget(layer_group)
        
        # Test buttons
        test_group = QtWidgets.QGroupBox("Tests")
        test_layout = QtWidgets.QVBoxLayout(test_group)
        
        self.load_btn = QtWidgets.QPushButton("Load Points")
        self.load_btn.clicked.connect(self._load_points)
        test_layout.addWidget(self.load_btn)
        
        self.clear_btn = QtWidgets.QPushButton("Clear All")
        self.clear_btn.clicked.connect(self._clear_all)
        test_layout.addWidget(self.clear_btn)
        
        self.zoom_test_btn = QtWidgets.QPushButton("Run Zoom Test")
        self.zoom_test_btn.clicked.connect(self._run_zoom_test)
        test_layout.addWidget(self.zoom_test_btn)
        
        layout.addWidget(test_group)
        
        # Performance stats
        stats_group = QtWidgets.QGroupBox("Performance Stats")
        stats_layout = QtWidgets.QVBoxLayout(stats_group)
        
        self.stats_label = QtWidgets.QLabel("No data yet")
        self.stats_label.setWordWrap(True)
        self.stats_label.setStyleSheet("font-family: monospace; font-size: 10px;")
        stats_layout.addWidget(self.stats_label)
        
        layout.addWidget(stats_group)
        
        # Selection info
        sel_group = QtWidgets.QGroupBox("Selection")
        sel_layout = QtWidgets.QVBoxLayout(sel_group)
        
        self.sel_label = QtWidgets.QLabel("No selection")
        self.sel_label.setWordWrap(True)
        sel_layout.addWidget(self.sel_label)
        
        layout.addWidget(sel_group)
        
        layout.addStretch()
        
        return panel
    
    def _on_map_ready(self):
        """Called when map is ready."""
        print("Map ready!")
        self.statusBar().showMessage("Map ready. Load points to start testing.", 5000)
        
        # Connect to selection changes
        self.map_widget.selectionChanged.connect(self._on_selection_changed)
    
    def _load_points(self):
        """Load points into the map."""
        count = self.count_spin.value()
        layer_type = self.layer_combo.currentText()
        
        self.statusBar().showMessage(f"Loading {count:,} points...", 0)
        QtWidgets.QApplication.processEvents()
        
        start_time = time.time()
        
        # Generate random points worldwide
        rng = np.random.default_rng(seed=42)
        lats = (rng.random(count) * 170) - 85  # -85 to 85
        lons = (rng.random(count) * 350) - 175  # -175 to 175
        coords = list(zip(lats.tolist(), lons.tolist()))
        ids = [f"pt{i}" for i in range(count)]
        
        # Clear existing layers
        self._clear_all()
        
        if layer_type in ["FastPoints", "Both"]:
            # Create FastPoints layer
            self.fast_layer = self.map_widget.add_fast_points_layer(
                "fast_points",
                selectable=True,
                style=FastPointsStyle(
                    radius=2.5,
                    default_rgba=(0, 180, 0, 180),
                    selected_radius=6.0,
                    selected_rgba=(255, 255, 0, 255)
                ),
                cell_size_m=1000.0
            )
            self.fast_layer.add_points(coords, ids=[f"fp{i}" for i in range(count)])
            print(f"Added {count:,} FastPoints")
        
        if layer_type in ["FastGeoPoints", "Both"]:
            # Create FastGeoPoints layer with random ellipses
            sma_m = (50 + rng.random(count) * 450).tolist()  # 50-500m
            smi_m = (30 + rng.random(count) * 220).tolist()  # 30-250m
            tilt_deg = (rng.random(count) * 360).tolist()
            
            self.fast_geo_layer = self.map_widget.add_fast_geopoints_layer(
                "fast_geo",
                selectable=True,
                style=FastGeoPointsStyle(
                    point_radius=2.5,
                    default_point_rgba=(40, 80, 255, 180),
                    selected_point_radius=6.0,
                    selected_point_rgba=(255, 255, 255, 255),
                    ellipse_stroke_rgba=(40, 80, 255, 120),
                    ellipse_stroke_width=1.0,
                    fill_ellipses=False,
                    ellipses_visible=True,
                    min_ellipse_px=1.0,
                    skip_ellipses_while_interacting=True
                ),
                cell_size_m=1000.0
            )
            self.fast_geo_layer.add_points_with_ellipses(
                coords=coords,
                sma_m=sma_m,
                smi_m=smi_m,
                tilt_deg=tilt_deg,
                ids=[f"geo{i}" for i in range(count)]
            )
            print(f"Added {count:,} FastGeoPoints with ellipses")
        
        elapsed = time.time() - start_time
        self.statusBar().showMessage(
            f"Loaded {count:,} points in {elapsed:.2f}s. "
            "Try zooming in/out and panning to test performance.",
            10000
        )
    
    def _clear_all(self):
        """Clear all layers."""
        if self.fast_layer:
            self.fast_layer.clear()
            self.fast_layer = None
        if self.fast_geo_layer:
            self.fast_geo_layer.clear()
            self.fast_geo_layer = None
        self.perf_data.clear()
        self.stats_label.setText("No data yet")
        self.sel_label.setText("No selection")
    
    def _run_zoom_test(self):
        """Run automated zoom test."""
        self.statusBar().showMessage("Running zoom test...", 0)
        # This would require implementing zoom control via JS bridge
        # For now, just show a message
        QtWidgets.QMessageBox.information(
            self,
            "Zoom Test",
            "Manually test zoom performance:\n\n"
            "1. Zoom out to world view (Shift+drag or mouse wheel)\n"
            "2. Observe render times in Performance Stats\n"
            "3. Zoom in to a region\n"
            "4. Pan around and observe smoothness\n"
            "5. Try drag-selecting points at different zoom levels"
        )
        self.statusBar().showMessage("Ready", 5000)
    
    def _on_js_event(self, event_type: str, payload_json: str):
        """Handle JavaScript events."""
        import json
        
        if event_type == "perf":
            data = json.loads(payload_json)
            self.perf_data.append(data)
            
            # Keep only recent data
            if len(self.perf_data) > 20:
                self.perf_data.pop(0)
            
            # Update stats display
            self._update_stats()
    
    def _update_stats(self):
        """Update performance statistics display."""
        if not self.perf_data:
            return
        
        # Get latest data
        latest = self.perf_data[-1]
        
        # Calculate averages from recent data
        recent = self.perf_data[-5:]
        avg_total = sum(float(d["times"]["total_ms"]) for d in recent) / len(recent)
        avg_query = sum(float(d["times"]["query_ms"]) for d in recent) / len(recent)
        avg_draw = sum(float(d["times"]["draw_ms"]) for d in recent) / len(recent)
        
        stats_text = (
            f"Latest Render:\n"
            f"  Points: {latest['point_count']:,}\n"
            f"  Batches: {latest.get('batch_count', 'N/A')}\n"
            f"  Query: {latest['times']['query_ms']} ms\n"
            f"  Draw: {latest['times']['draw_ms']} ms\n"
            f"  Total: {latest['times']['total_ms']} ms\n"
            f"\n"
            f"Avg (last 5):\n"
            f"  Total: {avg_total:.2f} ms\n"
            f"  Query: {avg_query:.2f} ms\n"
            f"  Draw: {avg_draw:.2f} ms\n"
            f"  FPS: ~{1000/avg_total:.1f}" if avg_total > 0 else "  FPS: N/A"
        )
        
        self.stats_label.setText(stats_text)
    
    def _on_selection_changed(self, selection):
        """Handle selection changes."""
        self.last_selection = selection
        count = len(selection.feature_ids) if selection.feature_ids else 0
        
        sel_text = (
            f"Layer: {selection.layer_id}\n"
            f"Selected: {count} points\n"
        )
        
        if count > 0 and count <= 5:
            sel_text += f"IDs: {', '.join(selection.feature_ids[:5])}"
        elif count > 5:
            sel_text += f"IDs: {', '.join(selection.feature_ids[:3])} ... (and {count-3} more)"
        
        self.sel_label.setText(sel_text)


def main():
    app = QtWidgets.QApplication(sys.argv)
    
    window = PerformanceTestWindow()
    window.show()
    
    print("\n" + "="*60)
    print("PERFORMANCE TEST - Large Point Rendering")
    print("="*60)
    print("\nInstructions:")
    print("1. Click 'Load Points' to add 100k points to the map")
    print("2. Zoom out to world view - observe performance")
    print("3. Zoom in to a region - should be fast and smooth")
    print("4. Pan around at different zoom levels")
    print("5. Try selecting points (click or drag-select)")
    print("6. Watch 'Performance Stats' for render times")
    print("\nExpected improvements:")
    print("- Zoomed-out views: Much faster (LOD/decimation active)")
    print("- Zoomed-in views: Same performance as before")
    print("- Selection: Should work correctly at all zoom levels")
    print("="*60 + "\n")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
