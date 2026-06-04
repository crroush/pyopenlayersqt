#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from typing import Optional

from PySide6 import QtCore, QtWidgets
from PySide6.QtGui import QAction, QColor

from pyopenlayersqt import OLMapWidget, PointStyle


class MapContextMenuDemo(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Map Right-Click Context Menu Demo")
        self.resize(1100, 700)

        self.map_widget = OLMapWidget(center=(37.7749, -122.4194), zoom=11)
        self.setCentralWidget(self.map_widget)

        self.layer = self.map_widget.add_vector_layer("editable_points", selectable=True)
        self._point_counter = 0

        self.layer.add_points(
            [(37.7749, -122.4194), (37.7845, -122.4091), (37.7682, -122.4319)],
            ids=["pt_1", "pt_2", "pt_3"],
            style=PointStyle(radius=6.0, fill_color=QColor("#1f77b4")),
        )
        self._point_counter = 3

        self.map_widget.jsEvent.connect(self._on_js_event)

    def _on_js_event(self, event_type: str, payload_json: str) -> None:
        if event_type != "contextmenu":
            return

        payload = self._parse_payload(payload_json)
        if payload is None:
            return

        x = int(payload.get("client_x", 0))
        y = int(payload.get("client_y", 0))
        lon = float(payload.get("lon", 0.0))
        lat = float(payload.get("lat", 0.0))
        layer_id = payload.get("layer_id")
        feature_id = payload.get("feature_id")

        menu = QtWidgets.QMenu(self)

        create_action = QAction("Create point here", self)
        create_action.triggered.connect(lambda: self._create_point(lat=lat, lon=lon))
        menu.addAction(create_action)

        if layer_id and feature_id:
            open_action = QAction(f"Open dialog for point {feature_id}", self)
            open_action.triggered.connect(
                lambda: self._show_feature_dialog(feature_id=str(feature_id), lat=lat, lon=lon)
            )
            menu.addAction(open_action)

        menu.addSeparator()
        copy_action = QAction("Copy coordinates", self)
        copy_action.triggered.connect(
            lambda: QtWidgets.QApplication.clipboard().setText(f"{lat:.6f}, {lon:.6f}")
        )
        menu.addAction(copy_action)

        global_pos = self.map_widget.mapToGlobal(QtCore.QPoint(x, y))
        menu.exec(global_pos)

    def _create_point(self, lat: float, lon: float) -> None:
        self._point_counter += 1
        new_id = f"pt_{self._point_counter}"
        self.layer.add_points(
            [(lat, lon)],
            ids=[new_id],
            style=PointStyle(radius=6.5, fill_color=QColor("#2ca02c")),
        )

    def _show_feature_dialog(self, feature_id: str, lat: float, lon: float) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "Point clicked",
            f"Feature: {feature_id}\nLatitude: {lat:.6f}\nLongitude: {lon:.6f}",
        )

    @staticmethod
    def _parse_payload(payload_json: str) -> Optional[dict]:
        try:
            return json.loads(payload_json) if payload_json else {}
        except Exception:
            return None


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    window = MapContextMenuDemo()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
