"""Movable vector feature demo."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6 import QtWidgets

from pyopenlayersqt import (
    CircleStyle,
    EllipseStyle,
    IconStyle,
    OLMapWidget,
    PointStyle,
    PolygonStyle,
    VectorVertexEditing,
)


class MovableVectorDemo(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Movable Vector Feature Demo")

        layout = QtWidgets.QVBoxLayout(self)
        instructions = QtWidgets.QLabel(
            "Movable Vector Feature Demo\n"
            "• Every vector feature type appears as movable and not movable.\n"
            "• Feature labels only say whether the object is movable.\n"
            "• Orange line and green polygon: existing vertices move.\n"
            "• Purple line and olive polygon: new vertices can be created.\n"
            "• Navy polygon and gradient line: whole-object movement only.\n"
            "• Red objects, including the red icon point, are not movable and should stay fixed."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        self.map_widget = OLMapWidget(center=(39.5, -98.0), zoom=4)
        layout.addWidget(self.map_widget, 1)
        self.map_widget.ready.connect(self._populate)
        self._populated = False

    def _populate(self) -> None:
        if self._populated:
            return
        self._populated = True
        layer = self.map_widget.add_vector_layer(
            "movable_vectors",
            selectable=True,
            movable=True,
            vertex_editing=VectorVertexEditing.MOVE,
        )
        self.vector_layer = layer
        red = "#d62728"

        layer.add_points(
            [(40.5, -122.0), (38.7, -121.0)],
            ids=["movable_point", "fixed_point"],
            style=PointStyle(radius=8, fill_color="#1f77b4"),
            properties=[{"label": "movable point"}, {"label": "not movable point"}],
            movable=[True, False],
        )

        icon_path = Path(__file__).resolve().parent / "assets" / "orange_pin.svg"
        red_pin = (
            "data:image/svg+xml;utf8,"
            "<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' "
            "viewBox='0 0 64 64'><path fill='%23d62728' stroke='black' "
            "d='M32 2C20 2 11 11 11 23c0 16 21 39 21 39s21-23 21-39C53 11 44 2 32 2z'/>"
            "<circle cx='32' cy='23' r='8' fill='white'/></svg>"
        )
        layer.add_icon_points(
            [(37.8, -119.5)],
            icon=str(icon_path),
            ids=["movable_icon_point"],
            movable=True,
            style=IconStyle(scale=0.8),
            properties=[{"label": "movable icon point"}],
        )
        layer.add_icon_points(
            [(36.6, -118.3)],
            icon=red_pin,
            ids=["fixed_icon_point"],
            movable=False,
            style=IconStyle(scale=0.8),
            properties=[{"label": "not movable icon point"}],
        )

        layer.add_line(
            [(45, -104), (44, -101), (45, -98)], "move_vertices_line",
            style=PolygonStyle(stroke_color="orange", stroke_width=4, fill=False),
            properties={"label": "movable line"}, movable=True,
            vertex_editing=VectorVertexEditing.MOVE,
        )
        layer.add_line(
            [(42.5, -104), (41.5, -101), (42.5, -98)], "modify_line",
            style=PolygonStyle(stroke_color="purple", stroke_width=4, fill=False),
            properties={"label": "movable line"}, movable=True,
            vertex_editing=VectorVertexEditing.MODIFY,
        )
        layer.add_line(
            [(40.0, -104), (39.0, -101), (40.0, -98)], "fixed_line",
            style=PolygonStyle(stroke_color=red, stroke_width=4, fill=False),
            properties={"label": "not movable line"}, movable=False,
        )

        layer.add_gradient_line(
            [(36.8, -104), (36.2, -101.5), (36.8, -99)], [0, 5, 10],
            "movable_gradient_line", properties={"label": "movable gradient line"},
            movable=True, vertex_editing=VectorVertexEditing.NONE,
        )
        layer.add_gradient_line(
            [(35.0, -104), (34.4, -101.5), (35.0, -99)], [10, 5, 0],
            "fixed_gradient_line", properties={"label": "not movable gradient line"},
            movable=False,
        )

        layer.add_polygon(
            [(45, -93), (44, -90), (42.5, -91.5), (43.2, -94)], "move_vertices_polygon",
            style=PolygonStyle(stroke_color="green", fill_color="green"),
            properties={"label": "movable polygon"}, movable=True,
            vertex_editing=VectorVertexEditing.MOVE,
        )
        layer.add_polygon(
            [(41.5, -93), (40.5, -90), (39, -91.5), (39.8, -94)], "modify_polygon",
            style=PolygonStyle(stroke_color="olive", fill_color="olive"),
            properties={"label": "movable polygon"}, movable=True,
            vertex_editing=VectorVertexEditing.MODIFY,
        )
        layer.add_polygon(
            [(38, -93), (37, -90), (35.5, -91.5), (36.3, -94)], "whole_polygon",
            style=PolygonStyle(stroke_color="navy", fill_color="navy"),
            properties={"label": "movable polygon"}, movable=True,
            vertex_editing=VectorVertexEditing.NONE,
        )
        layer.add_polygon(
            [(34.5, -93), (33.5, -90), (32, -91.5), (32.8, -94)], "fixed_polygon",
            style=PolygonStyle(stroke_color=red, fill_color=red),
            properties={"label": "not movable polygon"}, movable=False,
        )

        layer.add_circle(
            (42, -84),
            90000,
            "movable_circle",
            CircleStyle(stroke_color="#1f77b4"),
            {"label": "movable circle"},
            movable=True,
        )
        layer.add_circle(
            (39, -84),
            90000,
            "fixed_circle",
            CircleStyle(stroke_color=red, fill_color=red),
            {"label": "not movable circle"},
            movable=False,
        )
        layer.add_ellipse(
            (42, -78),
            150000,
            70000,
            35,
            "movable_ellipse",
            EllipseStyle(stroke_color="#17becf"),
            {"label": "movable ellipse"},
            movable=True,
        )
        layer.add_ellipse(
            (39, -78),
            150000,
            70000,
            -25,
            "fixed_ellipse",
            EllipseStyle(stroke_color=red, fill_color=red),
            {"label": "not movable ellipse"},
            movable=False,
        )


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = MovableVectorDemo()
    w.resize(1100, 800)
    w.show()
    sys.exit(app.exec())
