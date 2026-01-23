# pyopenlayersqt Examples

This directory contains working example scripts demonstrating various features of pyopenlayersqt.

## Running the Examples

Each example is a standalone Python script that can be run directly:

```bash
python examples/01_quick_start.py
python examples/02_complete_example.py
```

## Example Descriptions

### 01_quick_start.py

The most basic example showing:
- Creating a map widget with custom initial center and zoom
- Adding a vector layer
- Adding points with custom styling
- Displaying the map

**Key features:**
- Map centered on US West Coast (-120.0, 37.0) at zoom level 6
- Two points: San Francisco and Los Angeles
- Custom red circle markers

### 02_complete_example.py

A comprehensive example demonstrating:
- Map widget with custom initial view
- Multiple layer types (vector and fast points)
- Feature table widget integration
- Bidirectional selection synchronization
- Handling 10,000+ points efficiently

**Key features:**
- Map centered on US West Coast for optimal viewing
- 1 vector point (red marker at San Francisco)
- 10,000 fast points (green, scattered across western US)
- Feature table showing all features
- Click on map to select features (updates table)
- Click on table rows to select features (updates map)
- Efficient rendering with canvas-based fast points layer

### 03_measurement_mode.py

Interactive distance measurement mode:
- Enable/disable measurement mode
- Click to add measurement points
- Display geodesic distances
- Clear measurements

### 04_sortable_table.py

Feature table sorting capabilities:
- Automatic sorting enabled by default
- Per-column sortable configuration
- Custom sort keys for special sorting logic
- Support for ISO8601 timestamps, numbers, and strings

### 05_range_slider_filter.py

Range slider widget with map and table filtering:
- Dual-handle range sliders for numeric and timestamp filtering
- Filter 5,000 points by value (0-100) and timestamp (30-day range)
- Features hidden temporarily (not removed) and can be shown again
- Bidirectional sync between map, table, and filters
- Points colored by value (green=low, red=high)
- Reset filters to show all points

**Key features:**
- `RangeSliderWidget` for numeric values (0-100)
- `RangeSliderWidget` for ISO8601 timestamps
- `hide_features()` and `show_features()` on FastPointsLayer
- `hide_rows_by_keys()` and `show_rows_by_keys()` on FeatureTableWidget
- Live filtering updates as sliders are adjusted
- Info panel showing visible/hidden counts

### 06_selection_recoloring.py

Selection and color updating across all layer types:
- FastPointsLayer with per-point colors
- FastGeoPointsLayer with per-point colors and uncertainty ellipses
- VectorLayer with point features
- Select features by clicking (Ctrl/Cmd+click for multi-select)
- Change colors of selected features with buttons
- Demonstrates `set_colors()` method for fast layers
- Demonstrates `update_feature_styles()` method for vector layers

**Key features:**
- 5 vector points with different colors (large markers)
- 100 fast points with random colors (small markers)
- 50 fast geo points with uncertainty ellipses and random colors
- Click to select points on any layer
- Use color buttons to recolor selected items
- Shows how to update colors for selected items on any layer type

## Requirements

All examples require:
- Python >= 3.10
- PySide6 >= 6.5
- numpy >= 1.23 (for examples using random data)
- pyopenlayersqt (installed from this repository)

Install dependencies:
```bash
pip install PySide6 numpy
```

## Tips

- **Initial View**: Use the `center` and `zoom` parameters in `OLMapWidget()` to set the initial map view appropriate for your data
- **Performance**: For > 1000 points, use `FastPointsLayer` instead of `VectorLayer`
- **Selection**: Features are selectable by clicking or Ctrl+drag (box selection)
- **Table Sync**: The complete example shows how to keep map and table selections synchronized
- **Recoloring**: Use `set_colors()` for fast layers or `update_feature_styles()` for vector layers to change colors
