#!/usr/bin/env python3
"""
Example: Using Column Sorting in FeatureTableWidget

This example demonstrates the new sorting features added to the FeatureTableWidget:
- Automatic sorting enabled by default
- Per-column sortable configuration
- Custom sort keys for special sorting logic
- Ability to disable sorting globally

Requirements: PySide6
"""

import sys
from datetime import datetime

from PySide6 import QtWidgets

from pyopenlayersqt.features_table import FeatureTableWidget, ColumnSpec


def main():
    """Run the sortable table example."""
    app = QtWidgets.QApplication(sys.argv)

    # Example 1: Basic sortable table (default behavior)
    # All columns are sortable by default
    table1 = FeatureTableWidget(
        columns=[
            ColumnSpec("ID", lambda r: r.get("id")),
            ColumnSpec("Name", lambda r: r.get("name")),
            ColumnSpec("Value", lambda r: r.get("value")),
            ColumnSpec("Timestamp", lambda r: r.get("timestamp")),
        ],
        sorting_enabled=True  # This is the default
    )

    # Add sample data
    table1.append_rows([
        {
            "layer_id": "1", "feature_id": "a", "id": "003", "name": "Charlie",
            "value": 150, "timestamp": "2024-01-15T10:30:00Z"
        },
        {
            "layer_id": "1", "feature_id": "b", "id": "001", "name": "Alice",
            "value": 100, "timestamp": "2024-01-10T08:00:00Z"
        },
        {
            "layer_id": "1", "feature_id": "c", "id": "002", "name": "Bob",
            "value": 200, "timestamp": "2024-01-20T15:45:00Z"
        },
    ])

    # Example 2: Table with some non-sortable columns
    _table2 = FeatureTableWidget(
        columns=[
            ColumnSpec("ID", lambda r: r.get("id"), sortable=True),
            ColumnSpec("Name", lambda r: r.get("name"), sortable=True),
            ColumnSpec("Actions", lambda r: "Edit | Delete", sortable=False),  # Not sortable
        ],
    )

    # Example 3: Custom sort key for complex sorting
    # For example, sorting timestamps as datetime objects

    def parse_timestamp(ts_string):
        """Convert ISO8601 string to datetime for proper sorting"""
        if not ts_string:
            return datetime.min
        try:
            return datetime.fromisoformat(ts_string.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return datetime.min

    _table3 = FeatureTableWidget(
        columns=[
            ColumnSpec("Event", lambda r: r.get("event")),
            ColumnSpec(
                "Timestamp",
                lambda r: r.get("timestamp"),
                sort_key=parse_timestamp  # Custom sort key
            ),
        ],
    )

    # Example 4: Disable sorting after creation
    table4 = FeatureTableWidget()
    table4.set_sorting_enabled(False)  # Disable sorting

    # Show one of the tables
    window = QtWidgets.QMainWindow()
    window.setWindowTitle("Sortable Feature Table Example")
    window.setCentralWidget(table1)
    window.resize(800, 400)
    window.show()

    print("Feature Table Sorting Example")
    print("="*60)
    print("✓ Sorting is ENABLED by default")
    print("✓ Click column headers to sort")
    print("✓ Click again to reverse sort order")
    print("✓ ISO8601 timestamps sort correctly")
    print("✓ Numbers sort numerically")
    print("✓ Strings sort alphabetically")
    print("\nFeatures:")
    print("  - sortable=True/False per column")
    print("  - sort_key=function for custom sorting")
    print("  - sorting_enabled parameter")
    print("  - set_sorting_enabled() method")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
