"""Example: Interactive Plot with Map and Table Synchronization

Demonstrates the PlotWidget with synchronized selection across:
- Map (with points)
- Table (feature listing)
- Plot (scatter plot of feature properties)

Features:
- 50k random points for demonstration
- Click on plot/map/table to select points
- Selection syncs across all three views
- Delete selected points from all views
- Simple scatter plot (lat vs lon as example, but can be any numeric properties)
"""

import sys
import time

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from pyopenlayersqt import (
    FastPointsStyle,
    OLMapWidget,
    PlotAxisConfig,
    PlotConfig,
    PlotTrace,
    PlotTraceStyle,
    PlotWidget,
)
from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget


class PlotMapTableExample(QMainWindow):
    """Example application with synchronized plot, map, and table."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Plot-Map-Table Synchronization Example")
        self.resize(1400, 800)

        # Data storage
        self.fast_layer = None
        self.point_data = []  # List of dicts with point info

        # Setup UI
        self._setup_ui()

        # Generate sample data
        self._generate_sample_data()

    def _setup_ui(self):
        """Create the UI layout."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Top toolbar
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)

        # Main splitter (left: map+plot, right: table)
        main_splitter = QSplitter(Qt.Horizontal)
        
        # Left side splitter (top: map, bottom: plot)
        left_splitter = QSplitter(Qt.Vertical)
        
        # Map widget
        self.map_widget = OLMapWidget()
        self.map_widget.selectionChanged.connect(self._on_map_selection)
        left_splitter.addWidget(self.map_widget)
        
        # Plot widget
        plot_config = PlotConfig(
            title="Feature Plot",
            x_axis=PlotAxisConfig(label="Longitude", grid=True),
            y_axis=PlotAxisConfig(label="Latitude", grid=True),
            legend=True,
        )
        self.plot_widget = PlotWidget(config=plot_config)
        self.plot_widget.selectionChanged.connect(self._on_plot_selection)
        left_splitter.addWidget(self.plot_widget)
        
        left_splitter.setSizes([400, 400])
        main_splitter.addWidget(left_splitter)

        # Table widget
        self.table_widget = FeatureTableWidget(
            key_fn=lambda row: (row["layer_id"], row["feature_id"]),
            columns=[
                ColumnSpec("ID", lambda r: r["feature_id"]),
                ColumnSpec("Lat", lambda r: r["lat"], fmt=lambda v: f"{v:.6f}"),
                ColumnSpec("Lon", lambda r: r["lon"], fmt=lambda v: f"{v:.6f}"),
                ColumnSpec("Value", lambda r: r.get("value", 0.0), fmt=lambda v: f"{v:.2f}"),
            ],
        )
        self.table_widget.selectionKeysChanged.connect(self._on_table_selection)
        main_splitter.addWidget(self.table_widget)

        main_splitter.setSizes([900, 500])
        layout.addWidget(main_splitter)

        # Status bar
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

    def _create_toolbar(self):
        """Create the toolbar with action buttons."""
        toolbar = QWidget()
        layout = QHBoxLayout(toolbar)

        btn_generate = QPushButton("Generate 50k Points")
        btn_generate.clicked.connect(self._generate_sample_data)
        layout.addWidget(btn_generate)

        btn_clear_selection = QPushButton("Clear Selection")
        btn_clear_selection.clicked.connect(self._clear_all_selections)
        layout.addWidget(btn_clear_selection)

        btn_delete = QPushButton("Delete Selected")
        btn_delete.clicked.connect(self._delete_selected)
        layout.addWidget(btn_delete)

        btn_zoom = QPushButton("Zoom to Data")
        btn_zoom.clicked.connect(self._zoom_to_data)
        layout.addWidget(btn_zoom)

        layout.addStretch()
        return toolbar

    def _generate_sample_data(self):
        """Generate random sample data and add to map, table, and plot."""
        n_points = 50000
        self.status_label.setText(f"Generating {n_points} points...")
        QApplication.processEvents()

        # Generate random points
        rng = np.random.default_rng(seed=42)
        
        # Random coordinates (roughly over US)
        lons = -125.0 + rng.random(n_points) * 55.0  # -125 to -70
        lats = 25.0 + rng.random(n_points) * 25.0    # 25 to 50
        
        # Random values for demonstration
        values = rng.random(n_points) * 100.0

        # Clear existing data
        if self.fast_layer is not None:
            self.fast_layer.clear()
        self.table_widget.clear()
        self.plot_widget.clear_traces()
        self.point_data = []

        # Add to map (fast points layer)
        layer_id = f"points_{int(time.time())}"
        coords = [(float(lat), float(lon)) for lat, lon in zip(lats, lons)]
        ids = [f"pt_{i}" for i in range(n_points)]
        
        style = FastPointsStyle(
            point_radius=3,
            point_color=(66, 133, 244, 200),  # Blue with alpha
            selected_point_color=(255, 215, 0, 255),  # Gold when selected
        )
        
        self.fast_layer = self.map_widget.add_fast_points(
            coords, ids=ids, style=style, name="sample_points"
        )

        # Add to table
        rows = []
        for i, (lat, lon, val) in enumerate(zip(lats, lons, values)):
            row = {
                "layer_id": layer_id,
                "feature_id": ids[i],
                "lat": float(lat),
                "lon": float(lon),
                "value": float(val),
            }
            rows.append(row)
            self.point_data.append(row)
        
        self.table_widget.append_rows(rows)

        # Add to plot (scatter: lon vs lat with color based on value)
        trace_style = PlotTraceStyle(
            color="#4285F4",  # Google blue
            point_size=4,
            symbol="o",
            show_points=True,
            show_line=False,
            alpha=0.6,
        )
        
        trace = PlotTrace(
            name="Points",
            x_data=tuple(lons),
            y_data=tuple(lats),
            feature_ids=tuple(ids),
            layer_id=layer_id,
            style=trace_style,
        )
        
        self.plot_widget.add_trace(trace)
        self.plot_widget.auto_range()

        # Zoom map to data
        self._zoom_to_data()

        self.status_label.setText(f"Generated {n_points} points successfully")

    def _zoom_to_data(self):
        """Zoom map to show all data."""
        if not self.point_data:
            return
        
        lats = [p["lat"] for p in self.point_data]
        lons = [p["lon"] for p in self.point_data]
        
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)
        
        # Add 10% padding
        lat_pad = (lat_max - lat_min) * 0.1
        lon_pad = (lon_max - lon_min) * 0.1
        
        self.map_widget.fit_bounds(
            lat_min - lat_pad,
            lon_min - lon_pad,
            lat_max + lat_pad,
            lon_max + lon_pad,
        )

    def _on_map_selection(self, selection):
        """Handle selection change from map."""
        layer_id = getattr(selection, "layer_id", "")
        fids = list(getattr(selection, "feature_ids", []) or [])
        
        if not layer_id or not fids:
            return
        
        keys = [(layer_id, fid) for fid in fids]
        
        # Update table and plot
        self.table_widget.select_keys(keys, clear_first=True)
        self.plot_widget.select_keys(keys, clear_first=True)
        
        self.status_label.setText(f"Selected {len(keys)} points from map")

    def _on_table_selection(self, keys):
        """Handle selection change from table."""
        if not keys:
            self._clear_all_selections()
            return
        
        # Update map and plot
        self.plot_widget.select_keys(keys, clear_first=True)
        
        # Update map selection
        if self.fast_layer:
            fids = [fid for layer_id, fid in keys]
            self.map_widget.set_fast_points_selection(self.fast_layer.id, fids)
        
        self.status_label.setText(f"Selected {len(keys)} points from table")

    def _on_plot_selection(self, keys):
        """Handle selection change from plot."""
        if not keys:
            self._clear_all_selections()
            return
        
        # Update table and map
        self.table_widget.select_keys(keys, clear_first=True)
        
        # Update map selection
        if self.fast_layer:
            fids = [fid for layer_id, fid in keys]
            self.map_widget.set_fast_points_selection(self.fast_layer.id, fids)
        
        self.status_label.setText(f"Selected {len(keys)} points from plot")

    def _clear_all_selections(self):
        """Clear selections in all views."""
        self.table_widget.select_keys([], clear_first=True)
        self.plot_widget.clear_selection()
        
        if self.fast_layer:
            self.map_widget.set_fast_points_selection(self.fast_layer.id, [])
        
        self.status_label.setText("Cleared all selections")

    def _delete_selected(self):
        """Delete selected points from all views."""
        selected_keys = self.plot_widget.get_selected_keys()
        
        if not selected_keys:
            self.status_label.setText("No points selected")
            return
        
        # Delete from plot
        self.plot_widget.delete_selected()
        
        # Delete from table
        self.table_widget.remove_keys(selected_keys)
        
        # Delete from map
        if self.fast_layer:
            fids = [fid for layer_id, fid in selected_keys]
            self.fast_layer.remove_points(fids)
        
        # Update internal data
        selected_fids = {fid for _, fid in selected_keys}
        self.point_data = [
            p for p in self.point_data if p["feature_id"] not in selected_fids
        ]
        
        self.status_label.setText(f"Deleted {len(selected_keys)} points")


def main():
    """Run the example application."""
    app = QApplication(sys.argv)
    window = PlotMapTableExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
