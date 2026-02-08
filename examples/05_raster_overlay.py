#!/usr/bin/env python3
"""Raster Image Overlay (Heatmap)

This example demonstrates:
- Creating a custom raster image (heatmap visualization)
- Adding raster overlays to the map with geographic bounds
- Adjusting raster opacity
- Using matplotlib colormaps for visualization
- Generating heatmaps from scattered point data

Raster overlays are useful for visualizing continuous data like:
- Temperature maps
- Population density
- Probability distributions
- Any grid-based data
"""

import sys

import numpy as np
from PIL import Image
from PySide6 import QtWidgets

from pyopenlayersqt import OLMapWidget, RasterStyle


def generate_heatmap_image(width=512, height=512, seed=42):
    """Generate a simple heatmap image using inverse distance weighting.
    
    Returns:
        PIL Image in RGBA format
    """
    rng = np.random.default_rng(seed)
    
    # Generate random point locations and values
    n_points = 20
    point_x = rng.random(n_points) * width
    point_y = rng.random(n_points) * height
    point_values = rng.random(n_points)
    
    # Create grid for the heatmap
    x = np.arange(width)
    y = np.arange(height)
    grid_x, grid_y = np.meshgrid(x, y)
    
    # Inverse distance weighting to create smooth heatmap
    grid_values = np.zeros((height, width))
    for i in range(n_points):
        dist = np.sqrt((grid_x - point_x[i])**2 + (grid_y - point_y[i])**2)
        # Avoid division by zero
        dist = np.maximum(dist, 1.0)
        grid_values += point_values[i] / (dist + 10.0)
    
    # Normalize to 0-1 range
    grid_values = (grid_values - grid_values.min()) / (grid_values.max() - grid_values.min())
    
    # Apply colormap (using matplotlib-like colormap)
    # Create a viridis-like colormap manually
    colors = np.array([
        [68, 1, 84, 255],      # Dark purple
        [59, 82, 139, 255],    # Blue
        [33, 145, 140, 255],   # Teal
        [94, 201, 98, 255],    # Green
        [253, 231, 37, 255]    # Yellow
    ], dtype=np.uint8)
    
    # Map values to colors
    indices = (grid_values * (len(colors) - 1)).astype(int)
    indices = np.clip(indices, 0, len(colors) - 1)
    rgba = colors[indices]
    
    # Create PIL image
    img = Image.fromarray(rgba, mode='RGBA')
    return img


class RasterOverlayExample(QtWidgets.QMainWindow):
    """Raster overlay example window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Raster Image Overlay (Heatmap)")
        self.resize(1200, 800)

        # Create map centered on San Francisco Bay Area
        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=10)

        # Generate a heatmap image
        heatmap_img = generate_heatmap_image(512, 512)

        # Define geographic bounds for the image
        # [lon_min, lat_min, lon_max, lat_max] in EPSG:4326 (WGS84)
        bounds = [-122.5, 37.7, -122.35, 37.85]  # Covers San Francisco

        # Add the raster overlay
        self.raster_layer = self.map_widget.add_raster_image(
            image=heatmap_img,
            bounds=bounds,
            style=RasterStyle(opacity=0.6),
            name="heatmap"
        )

        # Create controls
        controls = self._create_controls()

        # Layout
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(controls)
        layout.addWidget(self.map_widget, stretch=1)
        self.setCentralWidget(container)

    def _create_controls(self):
        """Create control panel."""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(panel)

        # Info label
        info = QtWidgets.QLabel(
            "This heatmap overlay demonstrates raster image rendering. "
            "Adjust opacity to blend with the base map."
        )
        info.setWordWrap(True)
        layout.addWidget(info, stretch=1)

        # Opacity control
        opacity_group = QtWidgets.QGroupBox("Heatmap Opacity")
        opacity_layout = QtWidgets.QHBoxLayout(opacity_group)
        opacity_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        self.opacity_slider = QtWidgets.QSlider(QtWidgets.Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(60)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_layout.addWidget(self.opacity_slider)
        self.opacity_label = QtWidgets.QLabel("0.60")
        opacity_layout.addWidget(self.opacity_label)
        layout.addWidget(opacity_group)

        return panel

    def _on_opacity_changed(self, value):
        """Update raster layer opacity."""
        opacity = value / 100.0
        self.opacity_label.setText(f"{opacity:.2f}")
        if self.raster_layer:
            self.raster_layer.set_opacity(opacity)


def main():
    """Run the raster overlay example."""
    app = QtWidgets.QApplication(sys.argv)
    window = RasterOverlayExample()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
