#!/usr/bin/env python3
"""High-Performance Selection System Example

This example demonstrates the high-performance selection system with:
  - 100,000 points on the map
  - 100,000 rows in a sortable table
  - Bidirectional selection sync between map and table
  - Multiple selection patterns (1-to-1, 1-to-many, cross-table)
  - Performance metrics and monitoring
  - Configurable selection behaviors

Features demonstrated:
  1. Fully sortable table with 100K rows
  2. Cross-table and map selection with defined behaviors
  3. Bidirectional selection (optional toggle)
  4. High performance with large datasets
  5. Selection system (SelectionManager) for easy configuration

Requirements: PySide6, numpy
"""

import sys
import time
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from PySide6 import QtCore, QtWidgets

from pyopenlayersqt import (
    OLMapWidget,
    FeatureTableWidget,
    ColumnSpec,
    SelectionManager,
    SelectionManagerBuilder,
    FastPointsStyle,
)

# Type alias
FeatureKey = Tuple[str, str]


@dataclass
class PointData:
    """Data model for a point feature."""
    layer_id: str
    feature_id: str
    latitude: float
    longitude: float
    value: float
    category: str
    timestamp: str
    region: str
    
    
@dataclass
class RegionData:
    """Data model for region summary (for second table)."""
    layer_id: str
    feature_id: str  # region name as feature_id
    region: str
    point_count: int
    avg_value: float


class HighPerformanceSelectionWindow(QtWidgets.QMainWindow):
    """Main window demonstrating high-performance selection."""
    
    def __init__(self, num_points: int = 100000):
        super().__init__()
        self.setWindowTitle("High-Performance Selection System - 100K Points")
        self.num_points = num_points
        
        # Create map widget
        self.map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)
        
        # Data storage
        self.point_data: List[PointData] = []
        self.region_data: List[RegionData] = []
        
        # Layers
        self.points_layer = None
        
        # Tables
        self.points_table = None
        self.regions_table = None
        
        # Selection manager
        self.selection_manager: SelectionManager = None
        
        # UI components
        self.create_ui()
        
        # Connect to map ready signal
        self.map_widget.ready.connect(self.on_map_ready)
    
    def create_ui(self):
        """Create the user interface."""
        # Create tables
        self.create_points_table()
        self.create_regions_table()
        
        # Create control panel
        controls = self.create_controls()
        
        # Create stats panel
        stats_panel = self.create_stats_panel()
        
        # Layout: Controls | Map | Tables
        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.addWidget(controls)
        left_layout.addWidget(stats_panel)
        left_layout.addStretch()
        left_panel.setMaximumWidth(300)
        
        # Tables panel (vertical tabs)
        tables_panel = QtWidgets.QTabWidget()
        tables_panel.addTab(self.points_table, "Points (100K)")
        tables_panel.addTab(self.regions_table, "Regions")
        tables_panel.setMaximumWidth(600)
        
        # Main layout
        main_layout = QtWidgets.QHBoxLayout()
        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.map_widget, 1)
        main_layout.addWidget(tables_panel)
        
        container = QtWidgets.QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
    
    def create_points_table(self):
        """Create the main points table (100K rows)."""
        self.points_table = FeatureTableWidget(
            columns=[
                ColumnSpec("Feature ID", lambda r: r.feature_id),
                ColumnSpec(
                    "Latitude",
                    lambda r: r.latitude,
                    fmt=lambda v: f"{v:.6f}",
                    sort_key=float,
                ),
                ColumnSpec(
                    "Longitude",
                    lambda r: r.longitude,
                    fmt=lambda v: f"{v:.6f}",
                    sort_key=float,
                ),
                ColumnSpec(
                    "Value",
                    lambda r: r.value,
                    fmt=lambda v: f"{v:.2f}",
                    sort_key=float,
                ),
                ColumnSpec("Category", lambda r: r.category),
                ColumnSpec("Region", lambda r: r.region),
                ColumnSpec("Timestamp", lambda r: r.timestamp),
            ],
            key_fn=lambda r: (r.layer_id, r.feature_id),
            sorting_enabled=True,
            debounce_ms=100,  # Increased debounce for large datasets
        )
    
    def create_regions_table(self):
        """Create the regions summary table."""
        self.regions_table = FeatureTableWidget(
            columns=[
                ColumnSpec("Region", lambda r: r.region),
                ColumnSpec(
                    "Point Count",
                    lambda r: r.point_count,
                    sort_key=int,
                ),
                ColumnSpec(
                    "Avg Value",
                    lambda r: r.avg_value,
                    fmt=lambda v: f"{v:.2f}",
                    sort_key=float,
                ),
            ],
            key_fn=lambda r: (r.layer_id, r.feature_id),
            sorting_enabled=True,
        )
    
    def create_controls(self) -> QtWidgets.QWidget:
        """Create control panel."""
        group = QtWidgets.QGroupBox("Controls")
        layout = QtWidgets.QVBoxLayout()
        
        # Bidirectional toggle
        self.bidirectional_checkbox = QtWidgets.QCheckBox("Bidirectional Selection")
        self.bidirectional_checkbox.setChecked(True)
        self.bidirectional_checkbox.stateChanged.connect(self.on_bidirectional_changed)
        layout.addWidget(self.bidirectional_checkbox)
        
        # Cross-table selection toggle
        self.cross_table_checkbox = QtWidgets.QCheckBox("Cross-Table Selection")
        self.cross_table_checkbox.setChecked(True)
        self.cross_table_checkbox.setToolTip(
            "When enabled, selecting a region selects all its points"
        )
        self.cross_table_checkbox.stateChanged.connect(self.on_cross_table_changed)
        layout.addWidget(self.cross_table_checkbox)
        
        layout.addWidget(QtWidgets.QLabel(""))
        
        # Clear selection button
        clear_btn = QtWidgets.QPushButton("Clear All Selections")
        clear_btn.clicked.connect(self.on_clear_selections)
        layout.addWidget(clear_btn)
        
        # Random selection button
        random_btn = QtWidgets.QPushButton("Select Random 100")
        random_btn.clicked.connect(self.on_select_random)
        layout.addWidget(random_btn)
        
        # Select region button
        region_btn = QtWidgets.QPushButton("Select Region 'A'")
        region_btn.clicked.connect(lambda: self.on_select_region("A"))
        layout.addWidget(region_btn)
        
        group.setLayout(layout)
        return group
    
    def create_stats_panel(self) -> QtWidgets.QWidget:
        """Create performance statistics panel."""
        group = QtWidgets.QGroupBox("Performance Stats")
        layout = QtWidgets.QVBoxLayout()
        
        self.stats_label = QtWidgets.QLabel("No data yet")
        self.stats_label.setWordWrap(True)
        self.stats_label.setStyleSheet(
            "QLabel { font-family: monospace; font-size: 10px; }"
        )
        layout.addWidget(self.stats_label)
        
        # Update stats timer
        self.stats_timer = QtCore.QTimer(self)
        self.stats_timer.timeout.connect(self.update_stats_display)
        self.stats_timer.start(1000)  # Update every second
        
        group.setLayout(layout)
        return group
    
    def on_map_ready(self):
        """Called when the map is ready."""
        print("=" * 60)
        print("MAP READY - Generating test data")
        print(f"Creating {self.num_points:,} points...")
        
        start_time = time.perf_counter()
        
        # Generate test data
        self.generate_data()
        
        data_time = time.perf_counter() - start_time
        print(f"Data generation: {data_time:.2f}s")
        
        # Add layer to map
        layer_start = time.perf_counter()
        self.add_map_layer()
        layer_time = time.perf_counter() - layer_start
        print(f"Layer creation: {layer_time:.2f}s")
        
        # Populate tables
        table_start = time.perf_counter()
        self.populate_tables()
        table_time = time.perf_counter() - table_start
        print(f"Table population: {table_time:.2f}s")
        
        # Setup selection manager
        manager_start = time.perf_counter()
        self.setup_selection_manager()
        manager_time = time.perf_counter() - manager_start
        print(f"Selection manager setup: {manager_time:.2f}s")
        
        total_time = time.perf_counter() - start_time
        print(f"Total initialization: {total_time:.2f}s")
        print("=" * 60)
        print("Ready! Try:")
        print("  - Click on map points (Ctrl+Click for multi-select)")
        print("  - Select rows in the points table")
        print("  - Select a region to select all its points")
        print("  - Sort columns by clicking headers")
        print("  - Toggle bidirectional/cross-table selection")
        print("=" * 60)
    
    def generate_data(self):
        """Generate 100K random points with realistic data."""
        rng = np.random.default_rng(seed=42)
        n = self.num_points
        
        # Generate points in California area (roughly)
        # Latitude: 32-42, Longitude: -124 to -114
        lats = 32.0 + rng.random(n) * 10.0
        lons = -124.0 + rng.random(n) * 10.0
        
        # Values: 0-1000
        values = rng.random(n) * 1000
        
        # Categories: A, B, C, D (distribution: 40%, 30%, 20%, 10%)
        cat_choices = rng.choice(
            ['A', 'B', 'C', 'D'],
            size=n,
            p=[0.4, 0.3, 0.2, 0.1]
        )
        
        # Regions: split California into 5 regions
        region_choices = []
        for lat in lats:
            if lat < 34:
                region_choices.append('South')
            elif lat < 36:
                region_choices.append('Central South')
            elif lat < 38:
                region_choices.append('Central')
            elif lat < 40:
                region_choices.append('Central North')
            else:
                region_choices.append('North')
        
        # Timestamps (2024 dates)
        base_ts = 1704067200  # 2024-01-01 00:00:00 UTC
        timestamps = base_ts + rng.integers(0, 365 * 86400, n)
        
        # Placeholder layer_id - will be updated after layer creation
        layer_id = "PLACEHOLDER"
        
        # Create point data objects
        for i in range(n):
            self.point_data.append(PointData(
                layer_id=layer_id,
                feature_id=f"p{i}",
                latitude=float(lats[i]),
                longitude=float(lons[i]),
                value=float(values[i]),
                category=cat_choices[i],
                timestamp=time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(timestamps[i])),
                region=region_choices[i],
            ))
        
        # Generate region summary data
        regions = ['South', 'Central South', 'Central', 'Central North', 'North']
        for region in regions:
            region_points = [p for p in self.point_data if p.region == region]
            if region_points:
                self.region_data.append(RegionData(
                    layer_id="regions",
                    feature_id=region,
                    region=region,
                    point_count=len(region_points),
                    avg_value=sum(p.value for p in region_points) / len(region_points),
                ))
    
    def add_map_layer(self):
        """Add points layer to the map."""
        # Use FastPointsLayer for performance with 100K points
        self.points_layer = self.map_widget.add_fast_points_layer(
            "points",
            selectable=True,
            style=FastPointsStyle(
                radius=3.0,
                default_rgba=(100, 150, 255, 180),
                selected_radius=6.0,
                selected_rgba=(255, 255, 0, 255),
            )
        )
        
        # Update all point data with the actual layer_id
        # (layer gets an auto-generated ID like "fp_1", not "points")
        actual_layer_id = self.points_layer.id
        for point in self.point_data:
            point.layer_id = actual_layer_id
        
        # Add all points at once (batched)
        coords = [(p.latitude, p.longitude) for p in self.point_data]
        ids = [p.feature_id for p in self.point_data]
        
        # Color by category
        color_map = {
            'A': (255, 100, 100, 180),
            'B': (100, 255, 100, 180),
            'C': (100, 100, 255, 180),
            'D': (255, 255, 100, 180),
        }
        colors = [color_map[p.category] for p in self.point_data]
        
        self.points_layer.add_points(coords, ids=ids, colors_rgba=colors)
        
        print(f"Added {len(coords):,} points to map with layer_id={actual_layer_id}")
    
    def populate_tables(self):
        """Populate both tables with data."""
        # Points table - add all 100K rows
        self.points_table.append_rows(self.point_data)
        print(f"Added {len(self.point_data):,} rows to points table")
        
        # Regions table
        self.regions_table.append_rows(self.region_data)
        print(f"Added {len(self.region_data)} rows to regions table")
    
    def setup_selection_manager(self):
        """Setup the selection manager with links."""
        # Create manager with builder pattern
        builder = SelectionManagerBuilder()
        builder.set_map_widget(self.map_widget)
        builder.enable_performance_stats()
        builder.set_debounce_ms(50)
        
        # Link points table to points layer
        # IMPORTANT: Use the layer's actual ID, not its name
        builder.add_table_layer_link(
            self.points_table,
            self.points_layer.id,  # Use actual layer_id (e.g., "fp_1"), not name
            table_id="points_table",
            bidirectional=True,
        )
        
        # Link regions table to points table with key mapper
        # When a region is selected, select all points in that region
        def region_to_points_mapper(keys: List[FeatureKey]) -> List[FeatureKey]:
            """Map region keys to all point keys in those regions."""
            result = []
            for layer_id, feature_id in keys:
                # feature_id is the region name
                region = feature_id
                # Find all points in this region
                for point in self.point_data:
                    if point.region == region:
                        result.append((point.layer_id, point.feature_id))
            return result
        
        builder.add_table_table_link(
            self.regions_table,
            self.points_table,
            table1_id="regions_table",
            table2_id="points_table",
            bidirectional=False,  # One-way: region -> points
            key_mapper=region_to_points_mapper,
        )
        
        self.selection_manager = builder.build()
        
        print("Selection manager configured")
    
    def on_bidirectional_changed(self, state):
        """Handle bidirectional selection toggle."""
        enabled = state == QtCore.Qt.Checked
        # Update the link
        if self.selection_manager:
            self.selection_manager.set_link_enabled(
                self.points_layer.id, "points_table", enabled
            )
            print(f"Map -> Table selection: {'enabled' if enabled else 'disabled'}")
    
    def on_cross_table_changed(self, state):
        """Handle cross-table selection toggle."""
        enabled = state == QtCore.Qt.Checked
        if self.selection_manager:
            # Use the stored table ID
            self.selection_manager.set_link_enabled(
                "regions_table",
                "points_table",
                enabled
            )
            print(f"Cross-table selection: {'enabled' if enabled else 'disabled'}")
    
    def on_clear_selections(self):
        """Clear all selections."""
        if self.selection_manager:
            self.selection_manager.clear_all_selections()
            print("All selections cleared")
    
    def on_select_random(self):
        """Select 100 random points."""
        if not self.point_data:
            return
        
        # Select random 100 points
        indices = np.random.choice(len(self.point_data), size=min(100, len(self.point_data)), replace=False)
        keys = [(self.point_data[i].layer_id, self.point_data[i].feature_id) for i in indices]
        
        # Select in table (will propagate to map via selection manager)
        self.points_table.select_keys(keys)
        print(f"Selected {len(keys)} random points")
    
    def on_select_region(self, region: str):
        """Select a specific region (will select all its points)."""
        # Find the region in region data
        for r in self.region_data:
            if r.region == region:
                keys = [(r.layer_id, r.feature_id)]
                self.regions_table.select_keys(keys)
                print(f"Selected region '{region}' ({r.point_count} points)")
                return
    
    def update_stats_display(self):
        """Update the statistics display."""
        if not self.selection_manager:
            return
        
        stats = self.selection_manager.get_stats()
        
        # Count current selections
        points_selected = len(self.points_table.selected_keys())
        regions_selected = len(self.regions_table.selected_keys())
        
        text = f"""Data:
  Points: {len(self.point_data):,}
  Regions: {len(self.region_data)}

Current Selection:
  Points: {points_selected:,}
  Regions: {regions_selected}

Performance:
  Total updates: {stats.total_updates}
  Avg time: {stats.avg_time_ms:.2f}ms
  Min time: {stats.min_time_ms:.2f}ms
  Max time: {stats.max_time_ms:.2f}ms
  Last: {stats.last_update_ms:.2f}ms
        ({stats.last_item_count} items)
"""
        self.stats_label.setText(text)


def main():
    """Run the high-performance selection example."""
    app = QtWidgets.QApplication(sys.argv)
    
    # Parse command-line args for number of points
    num_points = 100000
    if len(sys.argv) > 1:
        try:
            num_points = int(sys.argv[1])
        except ValueError:
            print(f"Invalid number of points: {sys.argv[1]}, using default 100000")
    
    print("=" * 60)
    print("High-Performance Selection System Example")
    print("=" * 60)
    print(f"Initializing with {num_points:,} points...")
    print("This may take a few seconds...")
    print()
    
    window = HighPerformanceSelectionWindow(num_points=num_points)
    window.resize(1800, 900)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
