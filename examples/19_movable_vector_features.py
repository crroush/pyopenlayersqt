#!/usr/bin/env python3
"""Movable and Locked Vector Features

This example demonstrates editable vector objects:
- Drag movable objects to reposition the whole feature.
- Drag vertices to reshape movable lines and polygon-like shapes.
- Locked points/features stay fixed even when the layer is movable.
- Feature movement emits ``vectorFeatureChanged`` with the updated geometry.
"""

import json
import sys

from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import (
    CircleStyle,
    EllipseStyle,
    OLMapWidget,
    PointStyle,
    PolygonStyle,
)


class MovableVectorFeaturesExample(QtWidgets.QMainWindow):
    """Window showing movable and locked vector-layer objects."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Movable Vector Features")
        self.resize(1200, 800)

        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=11)
        self.map_widget.vectorFeatureChanged.connect(self._on_feature_changed)

        self.status = QtWidgets.QLabel("Move a feature or vertex to see updates here.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("font-weight: bold; color: #2b5cab;")

        self._add_demo_features()

        instructions = QtWidgets.QLabel(
            "Movable Vector Feature Demo\n"
            "• Drag any blue/purple/orange/green feature body to move the whole object.\n"
            "• Drag a line/polygon/circle/ellipse vertex handle to reshape it.\n"
            "• Red points and the red polygon are locked and cannot be moved.\n"
            "• Use VectorLayer.set_features_movable([...], False/True) to lock or unlock existing features."
        )
        instructions.setWordWrap(True)

        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(instructions)
        layout.addWidget(self.status)
        layout.addWidget(self.map_widget, stretch=1)
        self.setCentralWidget(container)

    def _add_demo_features(self):
        self.vector_layer = self.map_widget.add_vector_layer(
            "movable_shapes", selectable=True, movable=True
        )

        # Points: three movable, two locked.
        point_coords = [
            (37.7749, -122.4194),
            (37.7849, -122.4094),
            (37.7649, -122.4294),
            (37.795, -122.435),
            (37.755, -122.405),
        ]
        point_ids = [
            "movable_point_1",
            "movable_point_2",
            "movable_point_3",
            "locked_point_1",
            "locked_point_2",
        ]
        point_movable = [True, True, True, False, False]
        point_properties = [
            {"label": "movable point"},
            {"label": "movable point"},
            {"label": "movable point"},
            {"label": "locked point"},
            {"label": "locked point"},
        ]
        self.vector_layer.add_points(
            point_coords,
            ids=point_ids,
            properties=point_properties,
            movable=point_movable,
            style=PointStyle(
                radius=9,
                fill_color=QColor("dodgerblue"),
                stroke_color=QColor("white"),
                stroke_width=2,
            ),
        )
        # Re-style the locked points so they are visually distinct.
        self.vector_layer.update_feature_styles(
            ["locked_point_1", "locked_point_2"],
            [
                PointStyle(
                    radius=9,
                    fill_color=QColor("crimson"),
                    stroke_color=QColor("white"),
                    stroke_width=2,
                ),
                PointStyle(
                    radius=9,
                    fill_color=QColor("crimson"),
                    stroke_color=QColor("white"),
                    stroke_width=2,
                ),
            ],
        )

        self.vector_layer.add_line(
            [(37.72, -122.51), (37.76, -122.49), (37.79, -122.52)],
            feature_id="movable_line",
            movable=True,
            style=PolygonStyle(stroke_color=QColor("darkorange"), stroke_width=5),
            properties={"label": "movable line"},
        )

        self.vector_layer.add_polygon(
            [
                (37.81, -122.48),
                (37.84, -122.44),
                (37.815, -122.39),
                (37.79, -122.43),
            ],
            feature_id="movable_polygon",
            movable=True,
            style=PolygonStyle(
                stroke_color=QColor("seagreen"),
                stroke_width=3,
                fill_color=QColor(46, 139, 87, 70),
            ),
            properties={"label": "movable polygon"},
        )

        self.vector_layer.add_polygon(
            [
                (37.70, -122.38),
                (37.73, -122.35),
                (37.70, -122.31),
                (37.67, -122.35),
            ],
            feature_id="locked_polygon",
            movable=False,
            style=PolygonStyle(
                stroke_color=QColor("crimson"),
                stroke_width=3,
                fill_color=QColor(220, 20, 60, 45),
            ),
            properties={"label": "locked polygon"},
        )

        self.vector_layer.add_circle(
            (37.72, -122.43),
            radius_m=1800,
            feature_id="movable_circle",
            movable=True,
            segments=32,
            style=CircleStyle(
                stroke_color=QColor("mediumpurple"),
                stroke_width=3,
                fill_color=QColor(147, 112, 219, 60),
            ),
            properties={"label": "movable circle"},
        )

        self.vector_layer.add_ellipse(
            (37.83, -122.30),
            sma_m=2600,
            smi_m=1100,
            tilt_deg=35,
            feature_id="movable_ellipse",
            movable=True,
            segments=32,
            style=EllipseStyle(
                stroke_color=QColor("teal"),
                stroke_width=3,
                fill_color=QColor(0, 128, 128, 55),
            ),
            properties={"label": "movable ellipse"},
        )

    def _on_feature_changed(self, change):
        geometry_type = (change.get("geometry") or {}).get("type", "unknown")
        coords = (change.get("geometry") or {}).get("coordinates")
        coords_json = json.dumps(coords)
        summary = coords_json[:140] + ("..." if len(coords_json) > 140 else "")
        self.status.setText(
            f"{change.get('reason')} updated {change.get('feature_id')} "
            f"({geometry_type}): {summary}"
        )


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MovableVectorFeaturesExample()
    window.show()
    sys.exit(app.exec())
