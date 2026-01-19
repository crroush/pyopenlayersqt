"""Tests for features_table.py ConfigurableTableModel.

Tests the core table model logic without requiring a real Qt environment.
"""
from dataclasses import dataclass

from pyopenlayersqt.features_table import ConfigurableTableModel, ColumnSpec
from PySide6.QtCore import Qt, QModelIndex


@dataclass
class SampleRow:
    """Sample row object for testing."""
    layer_id: str
    feature_id: str
    name: str
    value: float


def sample_key_fn(row):
    """Key function for sample rows."""
    return (row.layer_id, row.feature_id)


def test_empty_model():
    """Test model with no rows."""
    columns = [
        ColumnSpec("Name", lambda r: r.name),
        ColumnSpec("Value", lambda r: r.value),
    ]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    
    assert model.rowCount() == 0
    assert model.columnCount() == 2
    assert model.rows == []


def test_rowcount_columncount():
    """Test rowCount and columnCount methods."""
    columns = [
        ColumnSpec("Col1", lambda r: r.name),
        ColumnSpec("Col2", lambda r: r.value),
        ColumnSpec("Col3", lambda r: r.layer_id),
    ]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    
    # Empty model
    assert model.rowCount() == 0
    assert model.columnCount() == 3
    
    # Add rows
    rows = [
        SampleRow("layer1", "f1", "Feature 1", 10.5),
        SampleRow("layer1", "f2", "Feature 2", 20.3),
    ]
    model.append_rows(rows)
    
    assert model.rowCount() == 2
    assert model.columnCount() == 3
    
    # Invalid parent should return 0
    invalid_index = QModelIndex()
    invalid_index._valid = True
    assert model.rowCount(invalid_index) == 0
    assert model.columnCount(invalid_index) == 0


def test_headerdata():
    """Test headerData method."""
    columns = [
        ColumnSpec("Name", lambda r: r.name),
        ColumnSpec("Value", lambda r: r.value),
        ColumnSpec("Layer", lambda r: r.layer_id),
    ]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    
    # Horizontal headers
    assert model.headerData(0, Qt.Horizontal, Qt.DisplayRole) == "Name"
    assert model.headerData(1, Qt.Horizontal, Qt.DisplayRole) == "Value"
    assert model.headerData(2, Qt.Horizontal, Qt.DisplayRole) == "Layer"
    assert model.headerData(3, Qt.Horizontal, Qt.DisplayRole) is None  # Out of range
    
    # Non-DisplayRole should return None
    assert model.headerData(0, Qt.Horizontal, Qt.ToolTipRole) is None
    
    # Vertical headers (row numbers, 1-indexed)
    model.append_rows([
        SampleRow("layer1", "f1", "Feature 1", 10.5),
        SampleRow("layer1", "f2", "Feature 2", 20.3),
    ])
    assert model.headerData(0, Qt.Vertical, Qt.DisplayRole) == "1"
    assert model.headerData(1, Qt.Vertical, Qt.DisplayRole) == "2"
    # Vertical headers don't validate row range, return section+1
    assert model.headerData(2, Qt.Vertical, Qt.DisplayRole) == "3"


def test_data_display_role():
    """Test data() method with DisplayRole."""
    columns = [
        ColumnSpec("Name", lambda r: r.name),
        ColumnSpec("Value", lambda r: r.value),
        ColumnSpec("Formatted", lambda r: r.value, fmt=lambda v: f"{v:.2f}"),
    ]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    
    rows = [
        SampleRow("layer1", "f1", "Feature 1", 10.567),
        SampleRow("layer1", "f2", "Feature 2", 20.3),
    ]
    model.append_rows(rows)
    
    # Create valid model indexes
    idx_0_0 = QModelIndex()
    idx_0_0._valid = True
    idx_0_0.row = lambda: 0
    idx_0_0.column = lambda: 0
    
    idx_0_1 = QModelIndex()
    idx_0_1._valid = True
    idx_0_1.row = lambda: 0
    idx_0_1.column = lambda: 1
    
    idx_0_2 = QModelIndex()
    idx_0_2._valid = True
    idx_0_2.row = lambda: 0
    idx_0_2.column = lambda: 2
    
    idx_1_0 = QModelIndex()
    idx_1_0._valid = True
    idx_1_0.row = lambda: 1
    idx_1_0.column = lambda: 0
    
    # Test data retrieval
    assert model.data(idx_0_0, Qt.DisplayRole) == "Feature 1"
    assert model.data(idx_0_1, Qt.DisplayRole) == "10.567"
    assert model.data(idx_0_2, Qt.DisplayRole) == "10.57"  # Formatted
    assert model.data(idx_1_0, Qt.DisplayRole) == "Feature 2"
    
    # Invalid index
    invalid_idx = QModelIndex()
    assert model.data(invalid_idx, Qt.DisplayRole) is None


def test_data_with_getter_exception():
    """Test data() returns empty string when getter raises exception."""
    def failing_getter(row):
        raise ValueError("Intentional failure")
    
    columns = [
        ColumnSpec("Name", lambda r: r.name),
        ColumnSpec("Failing", failing_getter),
    ]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    model.append_rows([SampleRow("layer1", "f1", "Feature 1", 10.5)])
    
    idx = QModelIndex()
    idx._valid = True
    idx.row = lambda: 0
    idx.column = lambda: 1
    
    # Should return empty string on exception
    assert model.data(idx, Qt.DisplayRole) == ""


def test_data_with_formatter_exception():
    """Test data() falls back to str() when formatter raises exception."""
    def failing_formatter(value):
        raise ValueError("Intentional formatter failure")
    
    columns = [
        ColumnSpec("Value", lambda r: r.value, fmt=failing_formatter),
    ]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    model.append_rows([SampleRow("layer1", "f1", "Feature 1", 10.5)])
    
    idx = QModelIndex()
    idx._valid = True
    idx.row = lambda: 0
    idx.column = lambda: 0
    
    # Should fall back to str(value)
    assert model.data(idx, Qt.DisplayRole) == "10.5"


def test_data_tooltip_role():
    """Test data() method with ToolTipRole."""
    def tooltip_fn(row):
        return f"Tooltip for {row.name}"
    
    columns = [
        ColumnSpec("Name", lambda r: r.name, tooltip=tooltip_fn),
        ColumnSpec("Value", lambda r: r.value),  # No tooltip
    ]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    model.append_rows([SampleRow("layer1", "f1", "Feature 1", 10.5)])
    
    idx_0_0 = QModelIndex()
    idx_0_0._valid = True
    idx_0_0.row = lambda: 0
    idx_0_0.column = lambda: 0
    
    idx_0_1 = QModelIndex()
    idx_0_1._valid = True
    idx_0_1.row = lambda: 0
    idx_0_1.column = lambda: 1
    
    # Test tooltip
    assert model.data(idx_0_0, Qt.ToolTipRole) == "Tooltip for Feature 1"
    assert model.data(idx_0_1, Qt.ToolTipRole) is None  # No tooltip defined


def test_data_tooltip_exception():
    """Test data() returns None when tooltip callable raises exception."""
    def failing_tooltip(row):
        raise RuntimeError("Tooltip error")
    
    columns = [
        ColumnSpec("Name", lambda r: r.name, tooltip=failing_tooltip),
    ]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    model.append_rows([SampleRow("layer1", "f1", "Feature 1", 10.5)])
    
    idx = QModelIndex()
    idx._valid = True
    idx.row = lambda: 0
    idx.column = lambda: 0
    
    # Should return None on exception
    assert model.data(idx, Qt.ToolTipRole) is None


def test_flags():
    """Test flags() method."""
    columns = [ColumnSpec("Name", lambda r: r.name)]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    model.append_rows([SampleRow("layer1", "f1", "Feature 1", 10.5)])
    
    valid_idx = QModelIndex()
    valid_idx._valid = True
    valid_idx.row = lambda: 0
    valid_idx.column = lambda: 0
    
    invalid_idx = QModelIndex()
    
    # Valid index should return ItemIsEnabled | ItemIsSelectable
    flags = model.flags(valid_idx)
    assert flags == (Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    
    # Invalid index should return ItemIsEnabled
    assert model.flags(invalid_idx) == Qt.ItemIsEnabled


def test_rows_property():
    """Test rows property."""
    columns = [ColumnSpec("Name", lambda r: r.name)]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    
    assert model.rows == []
    
    rows = [
        SampleRow("layer1", "f1", "Feature 1", 10.5),
        SampleRow("layer1", "f2", "Feature 2", 20.3),
    ]
    model.append_rows(rows)
    
    assert len(model.rows) == 2
    assert model.rows[0].name == "Feature 1"
    assert model.rows[1].name == "Feature 2"


def test_append_rows():
    """Test append_rows method."""
    columns = [ColumnSpec("Name", lambda r: r.name)]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    
    # Append first batch
    rows1 = [
        SampleRow("layer1", "f1", "Feature 1", 10.5),
        SampleRow("layer1", "f2", "Feature 2", 20.3),
    ]
    model.append_rows(rows1)
    assert model.rowCount() == 2
    
    # Append second batch
    rows2 = [
        SampleRow("layer1", "f3", "Feature 3", 30.7),
    ]
    model.append_rows(rows2)
    assert model.rowCount() == 3
    
    # Append duplicate (should be skipped)
    model.append_rows([SampleRow("layer1", "f1", "Duplicate", 99.9)])
    assert model.rowCount() == 3  # No change
    
    # Append empty list
    model.append_rows([])
    assert model.rowCount() == 3  # No change


def test_clear():
    """Test clear method."""
    columns = [ColumnSpec("Name", lambda r: r.name)]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    
    model.append_rows([
        SampleRow("layer1", "f1", "Feature 1", 10.5),
        SampleRow("layer1", "f2", "Feature 2", 20.3),
    ])
    assert model.rowCount() == 2
    
    model.clear()
    assert model.rowCount() == 0
    assert model.rows == []


def test_row_for_key():
    """Test row_for_key and row_for methods."""
    columns = [ColumnSpec("Name", lambda r: r.name)]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    
    model.append_rows([
        SampleRow("layer1", "f1", "Feature 1", 10.5),
        SampleRow("layer2", "f2", "Feature 2", 20.3),
        SampleRow("layer1", "f3", "Feature 3", 30.7),
    ])
    
    # Test row_for_key
    assert model.row_for_key(("layer1", "f1")) == 0
    assert model.row_for_key(("layer2", "f2")) == 1
    assert model.row_for_key(("layer1", "f3")) == 2
    assert model.row_for_key(("layer1", "f99")) is None  # Not found
    
    # Test row_for convenience method
    assert model.row_for("layer1", "f1") == 0
    assert model.row_for("layer2", "f2") == 1
    assert model.row_for("nonexistent", "key") is None


def test_key_for_row():
    """Test key_for_row method."""
    columns = [ColumnSpec("Name", lambda r: r.name)]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    
    model.append_rows([
        SampleRow("layer1", "f1", "Feature 1", 10.5),
        SampleRow("layer2", "f2", "Feature 2", 20.3),
    ])
    
    assert model.key_for_row(0) == ("layer1", "f1")
    assert model.key_for_row(1) == ("layer2", "f2")
    assert model.key_for_row(2) is None  # Out of range
    assert model.key_for_row(-1) is None  # Negative index


def test_row_data():
    """Test row_data method."""
    columns = [ColumnSpec("Name", lambda r: r.name)]
    model = ConfigurableTableModel(columns=columns, key_fn=sample_key_fn)
    
    rows = [
        SampleRow("layer1", "f1", "Feature 1", 10.5),
        SampleRow("layer2", "f2", "Feature 2", 20.3),
    ]
    model.append_rows(rows)
    
    row0 = model.row_data(0)
    assert row0 is not None
    assert row0.name == "Feature 1"
    assert row0.value == 10.5
    
    row1 = model.row_data(1)
    assert row1 is not None
    assert row1.name == "Feature 2"
    
    assert model.row_data(2) is None  # Out of range
    assert model.row_data(-1) is None  # Negative index
