import sys
import json
import numpy as np

from PySide6.QtCore import Qt, QItemSelectionModel
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QSplitter,
    QVBoxLayout,
    QLabel,
    QTableView,
    QSlider,
    QHBoxLayout,
)

from pyopenlayersqt import OLMapWidget, PointStyle, PolygonStyle


def ellipse_polygon_lonlat(lon0, lat0, sma_m, smi_m, tilt_deg_from_north, n=72):
    """
    Return a closed ring [[lon,lat], ...] approximating an ellipse.
    sma_m, smi_m: semi-major/minor in meters
    tilt_deg_from_north: clockwise from true north
    """
    # Local meters -> degrees approximation
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * np.cos(np.deg2rad(lat0))

    theta = np.linspace(0, 2 * np.pi, n, endpoint=False)
    # ellipse in its own frame: x_east, y_north (meters)
    x = sma_m * np.cos(theta)  # along "east" axis before rotation
    y = smi_m * np.sin(theta)  # along "north" axis before rotation

    # rotate by tilt relative to north: we define tilt clockwise from north.
    # Our (x,y) is (east,north). Rotation about origin:
    # If tilt=0 => major axis aligned with north => we want the sma along y.
    # So swap: build in a frame where major along north first:
    x0 = smi_m * np.cos(theta)  # east radius
    y0 = sma_m * np.sin(theta)  # north radius (major)

    ang = np.deg2rad(tilt_deg_from_north)
    c, s = np.cos(ang), np.sin(ang)
    # rotate in EN plane clockwise from north means rotate the EN coordinates by +ang:
    # standard rotation about origin in x(east),y(north):
    xr = c * x0 + s * y0
    yr = -s * x0 + c * y0

    lons = lon0 + (xr / m_per_deg_lon)
    lats = lat0 + (yr / m_per_deg_lat)

    ring = [[float(lon), float(lat)] for lon, lat in zip(lons, lats)]
    ring.append(ring[0])
    return ring


def circle_polygon_lonlat(lon0, lat0, radius_m, n=72):
    return ellipse_polygon_lonlat(
        lon0, lat0, radius_m, radius_m, tilt_deg_from_north=0.0, n=n
    )


def make_feature_polygon(fid, ring_lonlat, props=None):
    props = props or {}
    props = dict(props)
    props["id"] = fid
    return {
        "type": "Feature",
        "id": fid,
        "properties": props,
        "geometry": {
            "type": "Polygon",
            "coordinates": [ring_lonlat],  # single ring
        },
    }


def make_feature_point(fid, lon, lat, props=None):
    props = props or {}
    props = dict(props)
    props["id"] = fid
    props["lon"] = lon
    props["lat"] = lat
    return {
        "type": "Feature",
        "id": fid,
        "properties": props,
        "geometry": {
            "type": "Point",
            "coordinates": [lon, lat],
        },
    }


def main():
    app = QApplication(sys.argv)
    win = QMainWindow()
    win.setWindowTitle(
        "pyopenlayersqt demo: table selection, ellipses, polygons, terrain opacity"
    )

    splitter = QSplitter(Qt.Horizontal)
    win.setCentralWidget(splitter)

    # --- Left: map widget ---
    m = OLMapWidget(port=8000)
    splitter.addWidget(m)

    # --- Right: controls + table ---
    right = QWidget()
    rlayout = QVBoxLayout(right)

    info = QLabel("Selection: none")
    info.setWordWrap(True)

    # Terrain opacity slider
    row = QWidget()
    row_l = QHBoxLayout(row)
    row_l.setContentsMargins(0, 0, 0, 0)
    row_l.addWidget(QLabel("Terrain opacity"))
    opacity_slider = QSlider(Qt.Horizontal)
    opacity_slider.setRange(0, 100)
    opacity_slider.setValue(55)
    row_l.addWidget(opacity_slider)

    table = QTableView()
    model = QStandardItemModel(0, 4)
    model.setHorizontalHeaderLabels(["id", "lat", "lon", "z"])
    table.setModel(model)
    table.setSelectionBehavior(QTableView.SelectRows)
    table.setSelectionMode(QTableView.ExtendedSelection)

    rlayout.addWidget(info)
    rlayout.addWidget(row)
    rlayout.addWidget(table)

    splitter.addWidget(right)
    splitter.setSizes([950, 450])

    # --- Generate terrain-like samples (your suggested approach) ---
    rng = np.random.default_rng(7)
    n = 400
    lat0, lon0 = 37.7749, -122.4194  # SF
    lats = lat0 + rng.normal(0, 0.08, size=n)
    lons = lon0 + rng.normal(0, 0.10, size=n)
    z = (
        900 * np.exp(-((lats - lat0) ** 2 + (lons - lon0) ** 2) / 0.01)
        + 200 * np.sin(10 * (lats - lat0))
        + 120 * np.cos(8 * (lons - lon0))
        + rng.normal(0, 30, size=n)
    )

    points = []
    for i in range(n):
        points.append(
            {"id": i, "lat": float(lats[i]), "lon": float(lons[i]), "z": float(z[i])}
        )

    # Fill table
    for p in points:
        model.appendRow(
            [
                QStandardItem(str(p["id"])),
                QStandardItem(f'{p["lat"]:.6f}'),
                QStandardItem(f'{p["lon"]:.6f}'),
                QStandardItem(f'{p["z"]:.2f}'),
            ]
        )

    id_to_row = {p["id"]: i for i, p in enumerate(points)}

    # --- Dots (points) layer ---
    dots_style = PointStyle(radius=4, selected_radius=7)
    dots_layer = m.add_points("dots", points, style=dots_style)
    clip = [
        (lon0 - 0.12, lat0 - 0.06),
        (lon0 + 0.10, lat0 - 0.08),
        (lon0 + 0.14, lat0 + 0.06),
        (lon0 - 0.05, lat0 + 0.10),
        (lon0 - 0.12, lat0 - 0.06),
    ]

    # --- Terrain / heatmap-like raster overlay (IDW->PNG) ---
    terrain_layer = m.add_colormap_points(
        "terrain",
        points=points,
        resolution=(768, 768),
        neighbors=16,
        power=2.0,
        cmap="terrain",
        opacity=opacity_slider.value() / 100.0,
        clip_polygon=clip,
    )

    # Hook opacity slider
    def on_opacity_changed(v):
        m.set_opacity("terrain", v / 100.0)

    opacity_slider.valueChanged.connect(on_opacity_changed)

    # --- Circles (as polygons) ---
    circle_ring = circle_polygon_lonlat(lon0, lat0, radius_m=6000, n=96)
    circle_fc = {
        "type": "FeatureCollection",
        "features": [
            make_feature_polygon(
                "circle_1", circle_ring, {"kind": "circle", "radius_m": 6000}
            ),
        ],
    }
    m.add_geojson("circles", circle_fc, geom_type="polygon", style=PolygonStyle())

    # --- Ellipses (as polygons) ---
    ell1 = ellipse_polygon_lonlat(
        lon0 + 0.08, lat0 + 0.03, sma_m=9000, smi_m=3000, tilt_deg_from_north=35, n=96
    )
    ell2 = ellipse_polygon_lonlat(
        lon0 - 0.10, lat0 - 0.02, sma_m=7000, smi_m=5000, tilt_deg_from_north=110, n=96
    )

    ell_fc = {
        "type": "FeatureCollection",
        "features": [
            make_feature_polygon(
                "ellipse_1",
                ell1,
                {"kind": "ellipse", "sma_m": 9000, "smi_m": 3000, "tilt_deg": 35},
            ),
            make_feature_polygon(
                "ellipse_2",
                ell2,
                {"kind": "ellipse", "sma_m": 7000, "smi_m": 5000, "tilt_deg": 110},
            ),
        ],
    }
    m.add_geojson(
        "ellipses",
        ell_fc,
        geom_type="polygon",
        style=PolygonStyle(
            fill=(0, 200, 120, 70),
            stroke=(0, 200, 120, 220),
            stroke_width=2,
            selected_fill=(255, 50, 50, 90),
            selected_stroke=(255, 50, 50, 230),
            selected_stroke_width=2,
        ),
    )

    # --- Arbitrary polygon (example) ---
    poly_ring = [
        [lon0 - 0.05, lat0 + 0.10],
        [lon0 + 0.02, lat0 + 0.13],
        [lon0 + 0.08, lat0 + 0.07],
        [lon0 + 0.03, lat0 + 0.03],
        [lon0 - 0.05, lat0 + 0.10],
    ]
    poly_fc = {
        "type": "FeatureCollection",
        "features": [
            make_feature_polygon("poly_1", poly_ring, {"kind": "polygon"}),
        ],
    }
    m.add_geojson(
        "polys",
        poly_fc,
        geom_type="polygon",
        style=PolygonStyle(
            fill=(200, 120, 0, 70),
            stroke=(200, 120, 0, 220),
            stroke_width=3,
            selected_fill=(255, 50, 50, 90),
            selected_stroke=(255, 50, 50, 230),
            selected_stroke_width=3,
        ),
    )

    # --- Selection <-> table wiring ---
    suppress_table = {"flag": False}
    suppress_map = {"flag": False}

    def select_rows_by_ids(ids):
        sel = table.selectionModel()
        suppress_table["flag"] = True
        try:
            sel.blockSignals(True)
            sel.clearSelection()
            flags = (
                QItemSelectionModel.SelectionFlag.Select
                | QItemSelectionModel.SelectionFlag.Rows
            )
            for _id in ids:
                row = id_to_row.get(_id)
                if row is None:
                    continue
                idx0 = model.index(row, 0)
                sel.select(idx0, flags)
        finally:
            sel.blockSignals(False)
            suppress_table["flag"] = False

    def on_map_select(ev):
        # ev: {"type":"select","layer":"dots", "ids":[...], ...}
        if ev.get("layer") != "dots":
            return
        ids = [int(x) for x in ev.get("ids", [])]
        info.setText(
            f"Selected {len(ids)} dot(s): {ids[:12]}{'…' if len(ids)>12 else ''}"
        )
        if suppress_map["flag"]:
            return
        select_rows_by_ids(ids)

    m.on_select(on_map_select)

    def on_table_selection_changed(*_):
        if suppress_table["flag"]:
            return
        sel = table.selectionModel()
        rows = [idx.row() for idx in sel.selectedRows()]
        ids = []
        for r in rows:
            item = model.item(r, 0)
            if item is not None:
                ids.append(int(item.text()))

        suppress_map["flag"] = True
        try:
            m.set_selected_ids("dots", ids)
        finally:
            suppress_map["flag"] = False

    table.selectionModel().selectionChanged.connect(on_table_selection_changed)

    # Fit view roughly to the dot cloud
    m.fit_to_extent(
        (
            float(np.min(lons)),
            float(np.min(lats)),
            float(np.max(lons)),
            float(np.max(lats)),
        )
    )

    win.resize(1500, 900)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
