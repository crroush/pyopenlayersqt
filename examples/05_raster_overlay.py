#!/usr/bin/env python3
"""Raster Image Overlay with Polygon Masking

This example demonstrates:
- Creating raster images masked to ARBITRARY POLYGON SHAPES
- Different masking techniques (circle, triangle, hexagon, star, irregular)
- How to use polygon masks for non-rectangular raster data
- Adding raster overlays to the map with geographic bounds
- Adjusting raster opacity
- Generating heatmaps from scattered point data

Real-world use cases:
- Masking data to country/state/region boundaries
- Irregular geographic areas
- Custom shapes and zones
- Non-rectangular data visualization
- Temperature maps, population density, probability distributions
"""

import sys
import io
import math

import numpy as np
from PIL import Image, ImageDraw
from PySide6 import QtWidgets
from PySide6.QtCore import Qt

from pyopenlayersqt import OLMapWidget, RasterStyle


def generate_masked_heatmap(width=512, height=512, polygon=None, seed=42):
    """Generate a heatmap image masked to an arbitrary polygon shape.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        polygon: List of (x, y) tuples defining polygon vertices in pixel coordinates.
                 If None, no masking is applied (full rectangle).
        seed: Random seed for reproducibility

    Returns:
        bytes: PNG image data with alpha channel (transparent outside polygon)
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

    # Create PIL image and return as PNG bytes
    img = Image.fromarray(rgba, mode='RGBA')

    # Apply polygon mask if provided
    if polygon is not None:
        # Create a mask image (0 = transparent, 255 = opaque)
        mask = Image.new('L', (width, height), 0)
        draw = ImageDraw.Draw(mask)
        # Draw filled polygon on mask
        draw.polygon(polygon, fill=255)

        # Apply mask to alpha channel
        img.putalpha(mask)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _get_circle_polygon(width, height, num_points=50):
    """Generate polygon approximating a circle."""
    center_x, center_y = width / 2, height / 2
    radius = min(width, height) * 0.4
    points = []
    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        points.append((x, y))
    return points


def _get_triangle_polygon(width, height):
    """Generate equilateral triangle polygon."""
    center_x, center_y = width / 2, height / 2
    radius = min(width, height) * 0.4
    points = []
    for i in range(3):
        angle = 2 * math.pi * i / 3 - math.pi / 2  # Start from top
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        points.append((x, y))
    return points


def _get_hexagon_polygon(width, height):
    """Generate hexagon polygon."""
    center_x, center_y = width / 2, height / 2
    radius = min(width, height) * 0.4
    points = []
    for i in range(6):
        angle = 2 * math.pi * i / 6
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        points.append((x, y))
    return points


def _get_star_polygon(width, height):
    """Generate 5-pointed star polygon."""
    center_x, center_y = width / 2, height / 2
    outer_radius = min(width, height) * 0.4
    inner_radius = outer_radius * 0.4
    points = []
    for i in range(10):
        angle = 2 * math.pi * i / 10 - math.pi / 2  # Start from top
        radius = outer_radius if i % 2 == 0 else inner_radius
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        points.append((x, y))
    return points


def _get_irregular_polygon(width, height):
    """Generate an irregular custom polygon."""
    # Custom irregular shape (percentage-based coordinates)
    shape_pct = [
        (0.2, 0.3), (0.4, 0.2), (0.7, 0.3),
        (0.8, 0.5), (0.7, 0.7), (0.5, 0.8),
        (0.3, 0.7), (0.1, 0.5)
    ]
    return [(x * width, y * height) for x, y in shape_pct]


class RasterOverlayExample(QtWidgets.QMainWindow):
    """Raster overlay example with polygon masking."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Raster Image Overlay with Polygon Masking")
        self.resize(1200, 800)

        # Create map centered on San Francisco Bay Area
        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=10)

        # Define geographic bounds for the image
        # Two (lat, lon) tuples defining SW and NE corners
        self.bounds = [
            (37.7, -122.5),   # Southwest corner (lat, lon)
            (37.85, -122.35)  # Northeast corner (lat, lon)
        ]

        # Create controls first (so opacity_slider exists)
        controls = self._create_controls()

        # Start with rectangular (no mask)
        self.raster_layer = None
        self._update_raster_with_mask("Rectangle")

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
            "Demonstrate polygon masking for raster images. "
            "Select a shape to mask the heatmap overlay."
        )
        info.setWordWrap(True)
        layout.addWidget(info, stretch=1)

        # Mask shape selector
        mask_group = QtWidgets.QGroupBox("Polygon Mask")
        mask_layout = QtWidgets.QVBoxLayout(mask_group)

        shape_layout = QtWidgets.QHBoxLayout()
        shape_layout.addWidget(QtWidgets.QLabel("Shape:"))
        self.shape_combo = QtWidgets.QComboBox()
        self.shape_combo.addItems([
            "Rectangle",
            "Circle",
            "Triangle",
            "Hexagon",
            "Star",
            "Irregular"
        ])
        shape_layout.addWidget(self.shape_combo)

        update_btn = QtWidgets.QPushButton("Update Mask")
        update_btn.clicked.connect(self._on_update_mask)
        shape_layout.addWidget(update_btn)

        mask_layout.addLayout(shape_layout)
        layout.addWidget(mask_group)

        # Opacity control
        opacity_group = QtWidgets.QGroupBox("Heatmap Opacity")
        opacity_layout = QtWidgets.QHBoxLayout(opacity_group)
        opacity_layout.addWidget(QtWidgets.QLabel("Opacity:"))
        self.opacity_slider = QtWidgets.QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(60)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_layout.addWidget(self.opacity_slider)
        self.opacity_label = QtWidgets.QLabel("0.60")
        opacity_layout.addWidget(self.opacity_label)
        layout.addWidget(opacity_group)

        return panel

    def _get_polygon_for_shape(self, shape_name):
        """Get polygon points for the selected shape."""
        width, height = 512, 512

        if shape_name == "Rectangle":
            return None  # No mask = full rectangle
        elif shape_name == "Circle":
            return _get_circle_polygon(width, height)
        elif shape_name == "Triangle":
            return _get_triangle_polygon(width, height)
        elif shape_name == "Hexagon":
            return _get_hexagon_polygon(width, height)
        elif shape_name == "Star":
            return _get_star_polygon(width, height)
        elif shape_name == "Irregular":
            return _get_irregular_polygon(width, height)
        return None

    def _update_raster_with_mask(self, shape_name):
        """Generate and display heatmap with the selected mask shape."""
        # Get polygon for this shape
        polygon = self._get_polygon_for_shape(shape_name)

        # Generate masked heatmap
        heatmap_png = generate_masked_heatmap(512, 512, polygon=polygon)

        # Remove old raster layer if exists
        if self.raster_layer:
            self.raster_layer.remove()

        # Add new raster overlay
        # First parameter is the image data (PNG bytes), not a keyword argument
        self.raster_layer = self.map_widget.add_raster_image(
            heatmap_png,
            bounds=self.bounds,
            style=RasterStyle(opacity=self.opacity_slider.value() / 100.0),
            name=f"heatmap_{shape_name.lower()}"
        )

    def _on_update_mask(self):
        """Handle mask shape update."""
        shape_name = self.shape_combo.currentText()
        self._update_raster_with_mask(shape_name)

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
