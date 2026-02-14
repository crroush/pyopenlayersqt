#!/usr/bin/env python3
"""Load Data and Zoom Example

This example demonstrates the one-call auto-zoom workflow:
1. Load data into map layers
2. Click a button to zoom to all loaded data via ``fit_to_data()``

Use this to quickly validate the feature-driven auto-zoom behavior.
"""

import io
import sys

from PIL import Image, ImageDraw
from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import OLMapWidget, PointStyle, RasterStyle


def build_demo_raster_png(width: int = 512, height: int = 512) -> bytes:
    """Create a simple polygon-masked raster for fit-to-data testing."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fill a simple irregular polygon with semi-transparent blue
    poly = [
        (width * 0.10, height * 0.25),
        (width * 0.55, height * 0.15),
        (width * 0.88, height * 0.35),
        (width * 0.78, height * 0.78),
        (width * 0.28, height * 0.88),
        (width * 0.08, height * 0.55),
    ]
    draw.polygon(poly, fill=(45, 130, 255, 170), outline=(0, 0, 0, 220), width=3)

    # Add an inner polygon to make the shape visually distinct
    inner = [
        (width * 0.28, height * 0.35),
        (width * 0.62, height * 0.32),
        (width * 0.68, height * 0.62),
        (width * 0.35, height * 0.72),
    ]
    draw.polygon(inner, fill=(255, 200, 40, 180), outline=(20, 20, 20, 220), width=2)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class FitToDataExample(QtWidgets.QMainWindow):
    """Example window for testing fit_to_data()."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Load Data and Zoom Example")
        self.resize(1200, 800)

        self.map_widget = OLMapWidget(center=(20.0, 0.0), zoom=2)
        self.vector_layer = self.map_widget.add_vector_layer("loaded_features", selectable=True)
        self.raster_layer = None
        self.raster_bounds = [
            (33.0, -122.8),
            (38.8, -116.8),
        ]

        self._loaded = False
        self._build_ui()

    def _build_ui(self) -> None:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)

        controls = QtWidgets.QHBoxLayout()

        load_btn = QtWidgets.QPushButton("Load Sample Data")
        load_btn.clicked.connect(self._load_data)
        controls.addWidget(load_btn)

        zoom_btn = QtWidgets.QPushButton("Zoom to Loaded Data")
        zoom_btn.clicked.connect(self._zoom_to_data)
        controls.addWidget(zoom_btn)

        load_raster_btn = QtWidgets.QPushButton("Load Raster")
        load_raster_btn.clicked.connect(self._load_raster)
        controls.addWidget(load_raster_btn)

        reset_btn = QtWidgets.QPushButton("Reset to World View")
        reset_btn.clicked.connect(lambda: self.map_widget.set_view(center=(20.0, 0.0), zoom=2))
        controls.addWidget(reset_btn)

        controls.addStretch()

        self.status = QtWidgets.QLabel("Click 'Load Sample Data', then 'Zoom to Loaded Data'.")
        controls.addWidget(self.status)

        layout.addLayout(controls)
        layout.addWidget(self.map_widget, stretch=1)
        self.setCentralWidget(container)

    def _load_data(self) -> None:
        """Load California-only points so fit behavior is easy to verify."""
        self.vector_layer.clear()

        # Northern/Central California
        north_central_points = [
            (37.7749, -122.4194),  # San Francisco
            (38.5816, -121.4944),  # Sacramento
            (36.7378, -119.7871),  # Fresno
        ]

        # Southern California
        south_points = [
            (34.0522, -118.2437),  # Los Angeles
            (32.7157, -117.1611),  # San Diego
            (33.7455, -117.8677),  # Anaheim
        ]

        self.vector_layer.add_points(
            north_central_points,
            ids=["sf", "sac", "fre"],
            style=PointStyle(
                radius=8.0,
                fill_color=QColor("tomato"),
                stroke_color=QColor("black"),
                stroke_width=1.5,
            ),
        )

        self.vector_layer.add_points(
            south_points,
            ids=["la", "sd", "ana"],
            style=PointStyle(
                radius=8.0,
                fill_color=QColor("royalblue"),
                stroke_color=QColor("black"),
                stroke_width=1.5,
            ),
        )

        self._loaded = True
        self.status.setText("Data loaded: 6 points across California.")

    def _load_raster(self) -> None:
        """Load a simple in-memory raster overlay in California."""
        raster_png = build_demo_raster_png()

        if self.raster_layer is None:
            self.raster_layer = self.map_widget.add_raster_image(
                raster_png,
                bounds=self.raster_bounds,
                style=RasterStyle(opacity=0.45),
                name="demo_raster",
            )
        else:
            self.raster_layer.set_image(raster_png, bounds=self.raster_bounds)

        self.status.setText("Raster loaded in California extent.")

    def _zoom_to_data(self) -> None:
        """Fit map to all loaded layer data (points and/or raster)."""
        if not self._loaded and self.raster_layer is None:
            self.status.setText("Load points and/or raster first.")
            return

        self.map_widget.fit_to_data(padding_px=48, max_zoom=6, duration_ms=250)
        self.status.setText("Applied fit_to_data() across loaded map layers.")


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = FitToDataExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
