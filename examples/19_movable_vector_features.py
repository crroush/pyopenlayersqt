#!/usr/bin/env python3
"""Movable and Not-Movable Vector Features

This example demonstrates every vector feature type with at least one movable
object and one not-movable object.
"""

import json
import sys
from pathlib import Path

from PySide6 import QtWidgets
from PySide6.QtGui import QColor

from pyopenlayersqt import (
    CircleStyle,
    EllipseStyle,
    IconStyle,
    OLMapWidget,
    PointStyle,
    PolygonStyle,
    VectorVertexEditing,
)


class MovableVectorFeaturesExample(QtWidgets.QMainWindow):
    """Window showing movable and not-movable vector-layer objects."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Movable and Not-Movable Vector Features")
        self.resize(1200, 800)

        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=11)
        self.map_widget.vectorFeatureChanged.connect(self._on_feature_changed)

        self.status = QtWidgets.QLabel("Move a movable feature; not-movable features should stay fixed.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("font-weight: bold; color: #2b5cab;")

        self._add_demo_features()

        instructions = QtWidgets.QLabel(
            "Movable Vector Feature Demo\n"
            "• Every vector feature type appears as movable and not movable.\n"
            "• Movable examples are blue, orange, green, purple, teal, or navy.\n"
            "• Not-movable examples are red.\n"
            "• Drag movable objects; red objects should stay fixed."
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
            "movable_shapes",
            selectable=True,
            movable=True,
            vertex_editing=VectorVertexEditing.MOVE,
        )

        # Points: three movable, two not movable.
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
            "not_movable_point_1",
            "not_movable_point_2",
        ]
        point_movable = [True, True, True, False, False]
        point_properties = [
            {"label": "movable point"},
            {"label": "movable point"},
            {"label": "movable point"},
            {"label": "not movable point"},
            {"label": "not movable point"},
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
        # Re-style the not movable points so they are visually distinct.
        self.vector_layer.update_feature_styles(
            ["not_movable_point_1", "not_movable_point_2"],
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

        icon_path = Path(__file__).parent / "assets" / "orange_pin.svg"
        self.vector_layer.add_icon_points(
            [(37.805, -122.415)],
            icon=str(icon_path),
            ids=["movable_icon_point"],
            movable=True,
            style=IconStyle(scale=0.08),
            properties=[{"label": "movable icon point"}],
        )

        red_pin_svg = b"""<svg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 48 48'>
  <path d='M24 45S9 28.5 9 17a15 15 0 1 1 30 0c0 11.5-15 28-15 28z' fill='#dc143c' stroke='#7a0015' stroke-width='2'/>
  <circle cx='24' cy='17' r='6' fill='white'/>
</svg>"""
        self.vector_layer.add_icon_points(
            [(37.745, -122.455)],
            icon=red_pin_svg,
            ids=["not_movable_icon_point"],
            movable=False,
            style=IconStyle(scale=0.08),
            properties=[{"label": "not movable icon point"}],
        )

        self.vector_layer.add_line(
            [(37.72, -122.51), (37.76, -122.49), (37.79, -122.52)],
            feature_id="movable_line",
            movable=True,
            vertex_editing=VectorVertexEditing.MOVE,
            style=PolygonStyle(stroke_color=QColor("darkorange"), stroke_width=5),
            properties={"label": "movable line"},
        )

        self.vector_layer.add_line(
            [(37.69, -122.51), (37.715, -122.49), (37.735, -122.515)],
            feature_id="not_movable_line",
            movable=False,
            style=PolygonStyle(stroke_color=QColor("crimson"), stroke_width=5),
            properties={"label": "not movable line"},
        )

        self.vector_layer.add_gradient_line(
            [
                (37.735, -122.31),
                (37.755, -122.285),
                (37.785, -122.30),
                (37.81, -122.275),
            ],
            values=[0.0, 0.5, 1.0, 0.25],
            feature_id="movable_gradient_line",
            movable=True,
            vertex_editing=VectorVertexEditing.NONE,
            style=PolygonStyle(stroke_width=6),
            properties={"label": "movable gradient line"},
            interpolate_steps=8,
        )

        self.vector_layer.add_gradient_line(
            [
                (37.695, -122.30),
                (37.71, -122.275),
                (37.735, -122.29),
                (37.755, -122.26),
            ],
            segment_colors=[QColor("crimson")] * 3,
            feature_id="not_movable_gradient_line",
            movable=False,
            style=PolygonStyle(stroke_width=6),
            properties={"label": "not movable gradient line"},
            interpolate_steps=1,
        )

        self.vector_layer.add_polygon(
            [
                (37.81, -122.48),
                (37.84, -122.44),
                (37.815, -122.39),
                (37.79, -122.43),
            ],
            feature_id="movable_polygon_vertices",
            movable=True,
            vertex_editing=VectorVertexEditing.MOVE,
            style=PolygonStyle(
                stroke_color=QColor("seagreen"),
                stroke_width=3,
                fill_color=QColor(46, 139, 87, 70),
            ),
            properties={"label": "movable polygon"},
        )

        self.vector_layer.add_polygon(
            [
                (37.735, -122.39),
                (37.765, -122.365),
                (37.745, -122.335),
                (37.715, -122.36),
            ],
            feature_id="movable_polygon_body_only",
            movable=True,
            vertex_editing=VectorVertexEditing.NONE,
            style=PolygonStyle(
                stroke_color=QColor("navy"),
                stroke_width=3,
                fill_color=QColor(0, 0, 128, 50),
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
            feature_id="not_movable_polygon",
            movable=False,
            style=PolygonStyle(
                stroke_color=QColor("crimson"),
                stroke_width=3,
                fill_color=QColor(220, 20, 60, 45),
            ),
            properties={"label": "not movable polygon"},
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

        self.vector_layer.add_circle(
            (37.685, -122.43),
            radius_m=1300,
            feature_id="not_movable_circle",
            movable=False,
            segments=32,
            style=CircleStyle(
                stroke_color=QColor("crimson"),
                stroke_width=3,
                fill_color=QColor(220, 20, 60, 45),
            ),
            properties={"label": "not movable circle"},
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

        self.vector_layer.add_ellipse(
            (37.79, -122.245),
            sma_m=2100,
            smi_m=900,
            tilt_deg=-20,
            feature_id="not_movable_ellipse",
            movable=False,
            segments=32,
            style=EllipseStyle(
                stroke_color=QColor("crimson"),
                stroke_width=3,
                fill_color=QColor(220, 20, 60, 45),
            ),
            properties={"label": "not movable ellipse"},
        )

    def _on_feature_changed(self, change):
        geometry = change.get("geometry") or {}
        geometry_type = geometry.get("type", "unknown")
        details = geometry.get("coordinates") if "coordinates" in geometry else geometry
        details_json = json.dumps(details)
        summary = details_json[:140] + ("..." if len(details_json) > 140 else "")
        self.status.setText(
            f"{change.get('reason')} updated {change.get('feature_id')} "
            f"({geometry_type}): {summary}"
        )


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MovableVectorFeaturesExample()
    window.show()
    sys.exit(app.exec())
