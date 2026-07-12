# pyopenlayersqt

`pyopenlayersqt` is a PySide6 widget library for building desktop mapping applications in Python. It embeds an OpenLayers map in `QWebEngineView` and gives you Python classes for the things a desktop map tool normally needs: layers, styles, feature selection, feature tables, parent/child selection linking, range filters, and time histograms.

Use it when your data and application logic live in Python, but you want OpenLayers to handle the browser-grade map rendering and interaction.

<img width="803" height="467" alt="pyopenlayersqt map widget screenshot" src="https://github.com/user-attachments/assets/0d607680-b16a-46ed-9562-eeb00525cf02" />

## Contents

- [What you can build](#what-you-can-build)
- [Install](#install)
- [The mental model](#the-mental-model)
- [Quick start: put points on a map](#quick-start-put-points-on-a-map)
- [Feature guide](#feature-guide)
  - [Map widget](#map-widget)
  - [Layer system](#layer-system)
  - [Coordinate order](#coordinate-order)
  - [Styling](#styling)
  - [Selection](#selection)
  - [Feature tables](#feature-tables)
  - [Parent/child selection linking](#parentchild-selection-linking)
  - [Filtering](#filtering)
  - [Tiles, WMS, and raster overlays](#tiles-wms-and-raster-overlays)
  - [Measurement and view extent callbacks](#measurement-and-view-extent-callbacks)
- [Public API reference](#public-api-reference)
- [Examples](#examples)
- [Performance notes](#performance-notes)
- [API compatibility](#api-compatibility)
- [License](#license)
- [Contributing](#contributing)
- [Credits](#credits)

## What you can build

`pyopenlayersqt` is designed for Qt applications where a map is part of a larger workflow, not a standalone web page. Typical uses include:

- Review tools for detections, tracks, assets, incidents, sites, or survey records.
- Dashboards that display many points and let users select, filter, recolor, or hide them.
- Parent/child workflows such as regions -> sites, missions -> observations, or devices -> events.
- Time-window review tools where the user filters map features and table rows together.
- Desktop viewers for WMS services, XYZ tile services, generated rasters, and local overlays.
- Geolocation QA tools that show uncertainty ellipses next to point estimates.

## Install

```bash
pip install pyopenlayersqt
```

Requirements:

- Python >= 3.8
- PySide6 >= 6.5
- numpy >= 1.23
- pillow >= 10.0
- matplotlib >= 3.7

## The mental model

A `pyopenlayersqt` app usually has four pieces:

1. **The map widget**: `OLMapWidget` owns the embedded OpenLayers page and exposes Qt signals/methods.
2. **Layers**: you add vector, fast point, WMS, tile, or raster layers to the map. Each selectable feature should have a stable string ID.
3. **Python-side UI**: optional `FeatureTableWidget`, sliders, context menus, and normal Qt widgets sit next to the map.
4. **A shared ID contract**: map feature IDs and table row keys use the same `(layer_id, feature_id)` identity. This is what makes selection, filtering, deletion, and parent/child linking predictable.

The library deliberately keeps OpenLayers details behind Python objects. You add features from Python; the widget serializes commands to JavaScript; selection and measurement events come back as typed Python payloads.

## Quick start: put points on a map

```python
import sys
from PySide6 import QtWidgets
from PySide6.QtGui import QColor
from pyopenlayersqt import OLMapWidget, PointStyle

app = QtWidgets.QApplication(sys.argv)

map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)
points = map_widget.add_vector_layer("cities", selectable=True)

points.add_points(
    [(37.7749, -122.4194), (34.0522, -118.2437)],  # (lat, lon)
    ids=["sf", "la"],
    style=PointStyle(radius=8, fill_color=QColor("red")),
)

map_widget.show()
sys.exit(app.exec())
```

That example contains the main pattern used everywhere else:

- Create one `OLMapWidget`.
- Add a layer.
- Add data with stable IDs.
- Let Qt own the application window and event loop.

## Feature guide

This section describes the main features as product capabilities: what they do, why they exist, and how to use them in an application.

### Map widget

`OLMapWidget` is the object you put in a Qt layout. It owns the embedded browser page, initializes OpenLayers, and gives the rest of your Python code a normal Qt-facing API.

Use it when you need:

- A map inside a desktop Qt application rather than a separate web app.
- Python methods for adding/removing map data without writing JavaScript.
- Qt signals for selection, measurement, extent changes, readiness, and low-level JavaScript events.
- Programmatic control of center, zoom, base map visibility, country boundaries, and map fitting.

The widget is intentionally the integration boundary. Application code should talk to `OLMapWidget` and the layer objects it returns; it should not need to know how commands are serialized to OpenLayers.

```python
map_widget = OLMapWidget(center=(37.0, -120.0), zoom=6)
map_widget.set_view(center=(40.7128, -74.0060), zoom=12)
map_widget.fit_to_data(padding_px=32, max_zoom=14)
```

### Layer system

Layers separate different kinds of data and rendering strategies. Choosing the right layer matters because a small editable geometry layer and a million-point review layer have different performance and interaction needs.

| Layer/API | What it does | Why you would use it |
| --- | --- | --- |
| `add_vector_layer()` / `VectorLayer` | Draws points, icon points, polygons, lines, circles, ellipses, and gradient lines. | Use for mixed geometry, per-feature styling, editable/review-sized datasets, and examples where clarity matters more than raw point volume. |
| `add_fast_points_layer()` / `FastPointsLayer` | Draws many points with canvas rendering and a spatial index. | Use for large point clouds or event sets where selection, hide/show filtering, and recoloring need to stay responsive. |
| `add_fast_geopoints_layer()` / `FastGeoPointsLayer` | Draws high-volume points plus uncertainty ellipses. | Use for geolocation estimates, sensor fixes, or QA views where the uncertainty footprint is as important as the point. |
| `add_wms()` / `WMSLayer` | Adds a server-rendered WMS tile source. | Use when authoritative context comes from a GIS server and individual features are not managed by the widget. |
| `add_tile_layer()` | Adds an XYZ/OSM-style tile source. | Use for custom basemaps, internal tile servers, or reference layers. |
| `add_raster_image()` / `RasterLayer` | Places an image over geographic bounds. | Use for generated heatmaps, model output, screenshots, or local raster overlays. |

```python
from pyopenlayersqt import FastPointsStyle

fast = map_widget.add_fast_points_layer(
    "measurements",
    selectable=True,
    style=FastPointsStyle(radius=3, default_color="steelblue"),
)
fast.add_points(coords, ids=measurement_ids)
```

### Coordinate order

Python APIs use `LatLon`, an alias for `(lat, lon)`. OpenLayers internally uses longitude/latitude order, but the Python API keeps the domain-friendly latitude-first convention at its boundary.

```python
from pyopenlayersqt import LatLon

center: LatLon = (37.7749, -122.4194)
map_widget.set_center(center)
```

Why it matters: most mistakes in desktop mapping tools come from mixing coordinate order across libraries. Keep application data in `(lat, lon)` for `pyopenlayersqt` calls and let the widget handle the OpenLayers conversion.

### Styling

Style classes describe how data should look when it is sent to OpenLayers. They keep rendering choices close to the Python code that creates the layer.

Use styles to:

- Make categories visually distinct.
- Emphasize selected features with larger or brighter markers.
- Show uncertainty with ellipse stroke/fill choices.
- Reuse one style object for a batch of features.
- Use Qt-native `QColor` values directly from the rest of your UI.

```python
from PySide6.QtGui import QColor
from pyopenlayersqt import PointStyle, PolygonStyle, FastGeoPointsStyle

point_style = PointStyle(radius=6, fill_color=QColor("orange"), stroke_color="black")
polygon_style = PolygonStyle(stroke_color="#00aaff", fill_color="#00aaff", fill_opacity=0.15)
geo_style = FastGeoPointsStyle(default_color="yellow", selected_color="cyan")
```

`QColor`, CSS color strings, hex strings, and color names are supported by the style classes. Legacy RGBA tuple fields remain available for fast-layer compatibility, but new code should prefer `QColor` or strings.

### Selection

Selection is the main bridge between the map and the rest of the UI. Every selectable feature should have a stable feature ID. When users select on the map, `OLMapWidget.selectionChanged` emits a `FeatureSelection` containing the layer ID and selected feature IDs.

```python
from pyopenlayersqt import FeatureSelection


def on_map_selection(selection: FeatureSelection) -> None:
    print(selection.layer_id, selection.feature_ids)

map_widget.selectionChanged.connect(on_map_selection)
```

Why this design: IDs are cheap to pass across the Python/JavaScript boundary and they compose naturally with tables, deletion, filtering, and parent/child relationships. Instead of moving full row objects through map events, the map reports identity and your Python data model resolves the details.

Programmatic selection uses layer-specific methods on `OLMapWidget`:

```python
map_widget.set_vector_selection(vector_layer.id, ["sf"], emit=False)
map_widget.set_fast_points_selection(fast_layer.id, ["pt_1", "pt_2"], emit=False)
map_widget.set_fast_geopoints_selection(geo_layer.id, ["gps_1"], emit=False)
```

### Feature tables

`FeatureTableWidget` gives users a non-map view of the same objects. It is useful for sorting, inspecting attributes, right-click actions, batch selection, and filtering results that are hard to express spatially.

The table uses the same identity model as the map: each row has a `(layer_id, feature_id)` key.

```python
from pyopenlayersqt import ColumnSpec, FeatureTableWidget

table = FeatureTableWidget(
    columns=[
        ColumnSpec("Name", lambda row: row["name"]),
        ColumnSpec("Value", lambda row: row["value"], fmt=lambda value: f"{value:.1f}"),
    ],
    key_fn=lambda row: (fast_layer.id, row["id"]),
)
table.append_rows(rows)
```

Use table helpers for common application actions:

- `selected_keys()` returns selected `(layer_id, feature_id)` pairs for map operations.
- `select_feature_ids(layer_id, ids)` mirrors map selection into the table.
- `hide_rows_by_keys(keys)`, `show_rows_by_keys(keys)`, and `show_all_rows()` implement filtering without rebuilding the model.
- `remove_keys(keys)` removes known feature rows; `remove_where(predicate)` removes rows by row data.
- `set_row_provider(provider)` enables virtual/lazy row access for large tables.

Context menus are built around `TableContextMenuEvent`, so callbacks receive both identity (`keys`) and data (`rows`):

```python
from PySide6.QtWidgets import QMenu
from pyopenlayersqt import TableContextMenuEvent


def open_menu(event: TableContextMenuEvent) -> None:
    menu = QMenu()
    inspect = menu.addAction(f"Inspect {len(event.keys)} selected row(s)")
    if menu.exec(event.global_pos) == inspect:
        print(event.keys, event.rows)

table.contextMenuRequested.connect(open_menu)
```

### Parent/child selection linking

Many applications do not have one flat feature list. A user selects a region and expects sites to select; a user selects a device and expects related events to appear; a user clicks child records and expects the parent context to update. The linking helpers implement this pattern with explicit mapping dictionaries instead of ad hoc signal chains.

- `TableLink` says which table belongs to which map layer or metadata key space.
- `MultiSelectLink` is the general implementation: one parent table/layer can drive any number of named child table/layer pairs. Use it when a parent selection fans out to multiple child collections, or when the workflow may grow that way.
- `DualSelectLink` is intentionally smaller: it is a thin one-child wrapper around `MultiSelectLink` with `child=` and `parent_by_child=` arguments instead of a `kids={...}` dictionary. It is not a separate synchronization model; it exists to make the common two-view case easier to read.

`DualSelectLink` is redundant in capability but useful in ergonomics. Use it when you know there is exactly one child table/layer. Use `MultiSelectLink` when there is more than one child, when children are metadata-only, or when the UI is likely to expand.

```python
from pyopenlayersqt import MultiSelectLink, TableLink

link = MultiSelectLink(
    map_widget=map_widget,
    parent=TableLink(table=regions_table, layer=region_layer),
    kids={
        "sites": TableLink(table=sites_table, layer=sites_layer),
        "assets": TableLink(table=assets_table, layer=assets_layer),
    },
    parent_by_kid={
        "sites": site_id_to_region_id,
        "assets": asset_id_to_region_id,
    },
)

link.set_parent(["region_1"])
```

For one parent and one child, the same relationship can be written with `DualSelectLink` without inventing a child name:

```python
from pyopenlayersqt import DualSelectLink, TableLink

link = DualSelectLink(
    map_widget=map_widget,
    parent=TableLink(table=regions_table, layer=region_layer),
    child=TableLink(table=sites_table, layer=sites_layer),
    parent_by_child=site_id_to_region_id,
)
link.set_child(["site_1", "site_2"], clear_parent=True)
```

The important rule is that IDs must match in three places: the map feature ID, the table key, and the child-to-parent mapping dictionary.

### Filtering

Filtering should not require rebuilding the map on every user interaction. The fast layers and table widget expose hide/show APIs so sliders can adjust visibility while preserving selection and row identity.

Use `RangeSliderWidget` for numeric ranges or simple timestamp ranges:

```python
from pyopenlayersqt import RangeSliderWidget

slider = RangeSliderWidget(min_val=0.0, max_val=100.0, step=1.0, label="Value")


def apply_value_filter(lo: float, hi: float) -> None:
    visible = [row["id"] for row in rows if lo <= row["value"] <= hi]
    visible_set = set(visible)
    hidden = [row["id"] for row in rows if row["id"] not in visible_set]
    fast_layer.show_features(visible)
    fast_layer.hide_features(hidden)
    table.show_rows_by_keys([(fast_layer.id, fid) for fid in visible])
    table.hide_rows_by_keys([(fast_layer.id, fid) for fid in hidden])

slider.rangeChanged.connect(apply_value_filter)
```

Use `TimeHistogramSliderWidget` when users need to see the time distribution before choosing a window. It inherits the same range signal and adds histogram distribution methods:

```python
from pyopenlayersqt import TimeHistogramSliderWidget

slider = TimeHistogramSliderWidget(label="Observation time", show_x_axis=True)
slider.set_available_range("2024-01-01T00:00:00Z", "2024-01-31T23:59:59Z")
slider.set_distribution_values([row["timestamp"] for row in rows])
slider.rangeChanged.connect(apply_time_filter)
```

### Tiles, WMS, and raster overlays

Feature layers show your application data. Tile, WMS, and raster layers provide map context or generated imagery.

Use them when you need:

- A custom basemap or internal tile service.
- Authoritative GIS context from a WMS server.
- A generated overlay such as a heatmap, model output image, or local PNG.

```python
from pyopenlayersqt import TileLayerOptions, WMSOptions, RasterStyle

tiles = map_widget.add_tile_layer(
    TileLayerOptions(
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        opacity=0.8,
        attribution="© OpenStreetMap contributors",
    ),
    name="reference",
)

wms = map_widget.add_wms(
    WMSOptions(
        url="https://example.com/geoserver/wms",
        params={"LAYERS": "workspace:layer", "TILED": True},
        opacity=0.6,
    ),
    name="wms",
)

raster = map_widget.add_raster_image(
    image_url=png_bytes,
    bounds=[(34.0, -119.0), (35.0, -118.0)],  # southwest, northeast
    style=RasterStyle(opacity=0.7),
    name="heatmap",
)
```

These image-based layers can be shown, hidden, updated, and removed. They do not emit per-feature selections because they do not expose individual feature IDs to the widget.

### Measurement and view extent callbacks

Measurement mode is for applications where the user needs quick map-derived distances without leaving the workflow. Each click emits a `MeasurementUpdate` with the clicked coordinate and cumulative distance.

```python
from pyopenlayersqt import MeasurementUpdate


def on_measurement(update: MeasurementUpdate) -> None:
    print(update.point_index, update.lat, update.lon, update.cumulative_distance_m)

map_widget.on_measurement_updated(on_measurement)
map_widget.set_measure_mode(True)
```

Extent callbacks are for dynamic loading and viewport-aware refreshes. Use a one-shot extent request when you need the current bounds, or a debounced watcher when panning/zooming should trigger data loading.

```python
map_widget.get_view_extent(lambda extent: print(extent))

handle = map_widget.watch_view_extent(load_data_for_extent, debounce_ms=150)
# later: handle.close()
```

## Public API reference

This section lists the package-level public exports from `pyopenlayersqt`. The examples above show how the pieces fit together; this reference explains what each exported symbol is for.

### Map widget

| Symbol | Purpose |
| --- | --- |
| `OLMapWidget` | Main `QWebEngineView` map widget. Add layers, control the view, receive selection/measurement/extent signals. |

### Styles and options

| Symbol | Use it for | Key fields |
| --- | --- | --- |
| `PointStyle` | Circle marker points in `VectorLayer`. | `radius`, `fill_color`, `fill_opacity`, `stroke_color`, `stroke_width`, `stroke_opacity`. |
| `IconStyle` | Advanced image-icon point styling. Most callers use `VectorLayer.add_icon_points()` instead of creating it directly. | `icon_src`, `selected_icon_src`, `scale`, `opacity`, `anchor`, `rotation_deg`, `rotate_with_view`. |
| `PolygonStyle` | Polygons, lines, and gradient lines. | `stroke_color`, `stroke_width`, `stroke_opacity`, `fill_color`, `fill_opacity`, `fill`. |
| `CircleStyle` | Circle features added by center and radius. | Same outline/fill fields as polygon styles. |
| `EllipseStyle` | Vector ellipses. | Same outline/fill fields as polygon styles. |
| `RasterStyle` | Image overlay styling. | `opacity`. |
| `WMSOptions` | WMS layer configuration. | `url`, `params`, `opacity`. |
| `TileLayerOptions` | Generic XYZ/OSM tile layer configuration. | `url`, `opacity`, `attribution`. |
| `FastPointsStyle` | Fast point layer styling. | `radius`, `default_color`, `selected_color`, `selected_radius`; legacy RGBA tuple fields are still accepted. |
| `FastGeoPointsStyle` | Fast point + uncertainty ellipse styling. | Point color/radius fields plus ellipse stroke/fill visibility and color fields. |

### Payloads and type aliases

| Symbol | Purpose | Fields/shape |
| --- | --- | --- |
| `LatLon` | Public coordinate alias. | `(lat: float, lon: float)`. |
| `FeatureSelection` | Emitted by `OLMapWidget.selectionChanged`. | `layer_id`, `feature_ids`, `count`, `raw`. |
| `MeasurementUpdate` | Emitted by measurement callbacks. | `point_index`, `lat`, `lon`, `segment_distance_m`, `cumulative_distance_m`. |

### Layers

| Symbol | Created by | Main use |
| --- | --- | --- |
| `FastPointsLayer` | `OLMapWidget.add_fast_points_layer()` | High-volume selectable points with fast hide/show and recoloring. |
| `FastGeoPointsLayer` | `OLMapWidget.add_fast_geopoints_layer()` | High-volume points with uncertainty ellipses. |

`VectorLayer`, `WMSLayer`, `TileLayer`, and `RasterLayer` are returned by map methods but are not currently exported at package level. Use the objects returned from `OLMapWidget` methods rather than importing those classes directly.

### Tables and linking

| Symbol | Purpose |
| --- | --- |
| `ColumnSpec` | Defines one `FeatureTableWidget` column: label, getter, optional formatter, tooltip, sort key, and edit setter. |
| `FeatureTableWidget` | Reusable Qt table for feature rows and selection keys. |
| `ContextMenuActionSpec` | Declarative table context-menu action: label, callback, and whether it is enabled with no selection. |
| `TableContextMenuEvent` | Context-menu payload with selected keys, row indices, row data, and click positions. |
| `TableRowProvider` | Protocol for virtual/lazy table data sources. Implement it for very large tables. |
| `TableLink` | Binds one table to one layer or to a metadata-only `key_layer_id`. |
| `MultiSelectLink` | General parent/child synchronizer. Use for one parent linked to multiple named child table/layer pairs, or when the workflow may grow beyond one child. |
| `DualSelectLink` | One-child convenience wrapper around `MultiSelectLink`. Equivalent capability for the simple two-view case, but with clearer `child` / `parent_by_child` arguments. |

### Filter widgets

| Symbol | Purpose |
| --- | --- |
| `RangeSliderWidget` | Dual-handle numeric or ISO8601 timestamp range filter. Emits `rangeChanged(min_value, max_value)`. |
| `TimeHistogramSliderWidget` | ISO8601 range filter with a histogram. Inherits the `RangeSliderWidget` contract and adds distribution methods. |

### Version

`__version__` is exported at package level and resolves to the installed package version, with a local `pyproject.toml` fallback for editable checkouts.

## Examples

The `examples/` directory is the best next stop after the Quick Start:

- `01_basic_map_with_markers.py` - Basic map with styled markers.
- `02_layer_types_and_styling.py` - Vector geometry and style classes.
- `03_fast_points_performance.py` - Large point rendering.
- `04_wms_and_base_layers.py` - WMS and base-layer controls.
- `05_raster_overlay.py` - In-memory PNG/raster overlays.
- `06_geo_uncertainty_ellipses.py` - Fast geo-points with uncertainty ellipses.
- `07_feature_selection.py` - Map selection callbacks.
- `08_table_integration.py` - Map/table selection synchronization.
- `09_selection_and_recoloring.py` - Selection-driven recoloring.
- `10_range_slider_filtering.py` - Slider-based filtering.
- `11_measurement_tool.py` - Distance measurement mode.
- `12_coordinate_display.py` - Coordinate display toggle.
- `13_dual_table_linking.py` - `DualSelectLink` parent/child workflow.
- `16_metadata_only_table_linking.py` - Large parent layer linked to metadata-only child rows.
- `17_map_right_click_context_menu.py` - Map right-click context menus.
- `18_gradient_track_speed.py` - Segment color gradients for tracks.
- `19_virtual_feature_table.py` - Lazy/virtual table provider.

## Performance notes

- Prefer `FastPointsLayer` or `FastGeoPointsLayer` for large point sets.
- Keep feature IDs as short stable strings; they are used for selection, table keys, and mapping dictionaries.
- Use hide/show methods for interactive filtering instead of removing and re-adding features on every slider movement.
- Use `FeatureTableWidget.set_row_provider()` for very large tables so rows can be resolved lazily.
- Use `watch_view_extent(..., debounce_ms=...)` for dynamic loading instead of loading on every raw map movement.
- Raster overlays can be passed as bytes, which is useful for generated heatmaps.

## API compatibility

The package-level symbols listed in [Public API reference](#public-api-reference) are the documented public surface for application code. The important compatibility contracts are:

- Coordinates passed to Python APIs use `LatLon` / `(lat, lon)`.
- Selectable map objects are identified by caller-provided string feature IDs.
- Map/table synchronization uses `(layer_id, feature_id)` keys.
- `FeatureSelection`, `MeasurementUpdate`, `RangeSliderWidget.rangeChanged`, and `FeatureTableWidget.selectionKeysChanged` are the recommended callback contracts.
- Prefer documented widget, layer, and style classes over private JavaScript bridge details.

Legacy RGBA tuple style fields are still accepted for fast-layer styles. For new code, prefer `QColor`, color names, hex strings, or CSS strings where supported.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome. Please feel free to submit a Pull Request.

## Credits

Built with:

- [OpenLayers](https://openlayers.org/) - Maps and geospatial rendering
- [PySide6](https://doc.qt.io/qtforpython/) - Qt bindings for Python
- [NumPy](https://numpy.org/) - High-performance numerical operations
- [Pillow](https://python-pillow.org/) - Image processing for raster overlays
