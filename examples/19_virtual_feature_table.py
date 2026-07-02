#!/usr/bin/env python3
"""Minimal virtual/lazy FeatureTableWidget example.

This example shows how to display a large logical table without appending one
Python row object per row. The provider computes values and selection keys from
source row indices on demand.
"""

from __future__ import annotations

import sys

import numpy as np
from PySide6 import QtWidgets

from pyopenlayersqt.features_table import ColumnSpec, FeatureTableWidget


class ArrayBackedProvider:
    """Small virtual row provider backed by NumPy arrays."""

    def __init__(self, layer_id: str, values: np.ndarray) -> None:
        self.layer_id = str(layer_id)
        self.values = values

    def row_count(self) -> int:
        return int(self.values.size)

    def data(self, source_row: int, _column: int, column_spec: ColumnSpec) -> object:
        if column_spec.name == "Feature ID":
            return f"pt_{source_row}"
        if column_spec.name == "Value":
            return int(self.values[source_row])
        if column_spec.name == "Bucket":
            return int(self.values[source_row] // 100)
        return ""

    def key(self, source_row: int) -> tuple[str, str]:
        return (self.layer_id, f"pt_{source_row}")

    def row_for_key(self, key: tuple[str, str]) -> int | None:
        layer_id, feature_id = key
        if str(layer_id) != self.layer_id or not str(feature_id).startswith("pt_"):
            return None
        try:
            row = int(str(feature_id)[3:])
        except ValueError:
            return None
        return row if 0 <= row < self.row_count() else None

    def row_data(self, source_row: int) -> dict[str, object]:
        return {
            "layer_id": self.layer_id,
            "feature_id": f"pt_{source_row}",
            "value": int(self.values[source_row]),
            "bucket": int(self.values[source_row] // 100),
        }


class VirtualFeatureTableExample(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Virtual FeatureTableWidget")
        self.resize(700, 500)

        self.status = QtWidgets.QLabel("Select table rows to see selected keys.")
        self.table = FeatureTableWidget(
            columns=[
                ColumnSpec("Feature ID", lambda row: row.get("feature_id", "")),
                ColumnSpec("Value", lambda row: row.get("value", "")),
                ColumnSpec("Bucket", lambda row: row.get("bucket", "")),
            ],
            sorting_enabled=False,
        )
        values = np.arange(250_000, dtype=np.int32)
        self.provider = ArrayBackedProvider("virtual_points", values)
        self.table.set_row_provider(self.provider)
        self.table.selectionKeysChanged.connect(self._on_selection)

        select_button = QtWidgets.QPushButton("Select rows 10-20 via feature IDs")
        select_button.clicked.connect(self._select_range)

        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.addWidget(self.status)
        layout.addWidget(select_button)
        layout.addWidget(self.table, stretch=1)
        self.setCentralWidget(container)

    def _select_range(self) -> None:
        self.table.select_feature_ids(
            "virtual_points", [f"pt_{i}" for i in range(10, 21)]
        )

    def _on_selection(self, keys: list[tuple[str, str]]) -> None:
        preview = ", ".join(feature_id for _layer_id, feature_id in keys[:8])
        suffix = "..." if len(keys) > 8 else ""
        self.status.setText(f"Selected {len(keys)} rows: {preview}{suffix}")


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    window = VirtualFeatureTableExample()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
