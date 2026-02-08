# pyopenlayersqt Examples

This directory contains comprehensive example scripts demonstrating all features of pyopenlayersqt.

**All examples use QColor for styling (RGBA tuples are deprecated).**

## Running the Examples

Each example is a standalone Python script:

```bash
python examples/01_basic_map_with_markers.py
```

## Requirements

```bash
pip install PySide6 numpy Pillow
```

## Examples

### 01_basic_map_with_markers.py
Basic map with QColor markers - **start here!**

### 02_layer_types_and_styling.py
All geometry types with QColor styling

### 03_fast_points_performance.py
High-performance rendering (10,000+ points)

### 04_wms_and_base_layers.py
WMS integration and opacity control

### 05_raster_overlay.py
Raster/heatmap visualization

### 06_geo_uncertainty_ellipses.py
Geolocation uncertainty with ellipses

### 07_feature_selection.py
Interactive selection across layers

### 08_table_integration.py ⭐ CORE
Bidirectional map-table sync

### 09_selection_and_recoloring.py ⭐ CORE
Interactive recoloring

### 10_range_slider_filtering.py
Range slider filtering

### 11_measurement_tool.py
Distance measurement

### 12_coordinate_display.py
Coordinate display toggle

## Code Quality

✅ All examples use QColor (RGBA deprecated)
✅ Pylint 10.00/10 rating
✅ PEP 8 compliant
