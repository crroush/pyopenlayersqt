"""Minimal example: Map + Table + Plot integration.

This is a simplified example showing the basic integration of:
- Map widget (spatial view)
- Table widget (tabular view)  
- Plot widget (chart view)

With bidirectional selection synchronization between all three views.

Uses a small dataset (1000 points) for quick startup and easy experimentation.
"""

import sys
from datetime import datetime, timedelta

from PySide6 import QtWidgets
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from pyopenlayersqt import (
    OLMapWidget,
    FastPointsStyle,
    PlotWidget,
    TraceStyle,
)
from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget


def create_sample_data(n=1000):
    """Create a small sample dataset for demonstration."""
    import numpy as np
    
    rng = np.random.default_rng(42)
    
    # Random locations in USA
    lats = 30.0 + rng.random(n) * 15.0
    lons = -120.0 + rng.random(n) * 30.0
    
    # Time series over last 7 days
    base = datetime.now() - timedelta(days=7)
    times = [base + timedelta(seconds=i * 7 * 86400 / n) for i in range(n)]
    
    # Some value (e.g., temperature)
    values = 15.0 + 10.0 * np.sin(np.linspace(0, 4 * np.pi, n)) + rng.normal(0, 2, n)
    
    data = []
    for i in range(n):
        data.append({
            "layer_id": "sample",
            "feature_id": str(i),
            "lat": float(lats[i]),
            "lon": float(lons[i]),
            "time": times[i].isoformat(),
            "time_unix": times[i].timestamp(),
            "value": float(values[i]),
        })
    
    return data


class MinimalExample(QMainWindow):
    """Minimal map+table+plot window."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Minimal: Map + Table + Plot")
        self.resize(1400, 700)
        
        # Generate data
        self.data = create_sample_data(1000)
        
        # Build UI
        self._setup_ui()
        
        # Populate widgets
        self._populate_map()
        self._populate_table()
        self._populate_plot()
        
    def _setup_ui(self):
        """Create the UI layout."""
        widget = QWidget()
        self.setCentralWidget(widget)
        layout = QHBoxLayout(widget)
        
        splitter = QSplitter(Qt.Horizontal)
        
        # Left: Map
        self.map = OLMapWidget(center=(37.5, -105.0), zoom=5)
        self.map.selectionChanged.connect(self._on_map_sel)
        
        # Center: Table
        self.table = FeatureTableWidget(
            columns=[
                ColumnSpec("ID", lambda r: r["feature_id"][:6]),
                ColumnSpec("Lat", lambda r: r["lat"], fmt=lambda v: f"{v:.2f}"),
                ColumnSpec("Lon", lambda r: r["lon"], fmt=lambda v: f"{v:.2f}"),
                ColumnSpec("Value", lambda r: r["value"], fmt=lambda v: f"{v:.1f}"),
            ],
            key_fn=lambda r: (r["layer_id"], r["feature_id"]),
        )
        self.table.selectionKeysChanged.connect(self._on_table_sel)
        
        # Right: Plot
        plot_container = QWidget()
        plot_layout = QVBoxLayout(plot_container)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        
        self.plot = PlotWidget()
        self.plot.selectionKeysChanged.connect(self._on_plot_sel)
        plot_layout.addWidget(self.plot)
        
        # Add widgets to splitter
        splitter.addWidget(self.map)
        splitter.addWidget(self.table)
        splitter.addWidget(plot_container)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 2)
        
        layout.addWidget(splitter)
        
    def _populate_map(self):
        """Add data to map."""
        layer = self.map.add_fast_points_layer(
            "sample",
            selectable=True,
            style=FastPointsStyle(
                radius=3.0,
                default_rgba=(50, 150, 250, 200),
                selected_radius=7.0,
                selected_rgba=(255, 200, 0, 255),
            ),
        )
        
        points = [{"id": d["feature_id"], "lat": d["lat"], "lon": d["lon"]} for d in self.data]
        layer.add_points(points)
        
        self.layer = layer
        
    def _populate_table(self):
        """Add data to table."""
        self.table.append_rows(self.data)
        
    def _populate_plot(self):
        """Add data to plot."""
        self.plot.set_data(
            data_rows=self.data,
            key_fn=lambda r: (r["layer_id"], r["feature_id"]),
            x_field="time_unix",
            y_field="value",
            trace_style=TraceStyle(color="#3296fa", symbol='o', symbol_size=4.0),
        )
        
    def _on_map_sel(self, sel):
        """Sync map selection to table and plot."""
        keys = [(sel.layer_id, str(fid)) for fid in sel.feature_ids]
        self.table.select_keys(keys, clear_first=True)
        self.plot.select_keys(keys, clear_first=True)
        
    def _on_table_sel(self, keys):
        """Sync table selection to map and plot."""
        if keys:
            fids = [fid for _, fid in keys]
            self.map.set_fast_points_selection(self.layer.id, fids)
        else:
            self.map.set_fast_points_selection(self.layer.id, [])
        self.plot.select_keys(keys, clear_first=True)
        
    def _on_plot_sel(self, keys):
        """Sync plot selection to table (which syncs to map)."""
        self.table.select_keys(keys, clear_first=True)


def main():
    """Run the minimal example."""
    app = QtWidgets.QApplication(sys.argv)
    window = MinimalExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
