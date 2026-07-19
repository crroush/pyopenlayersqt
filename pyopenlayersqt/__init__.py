from .widget import OLMapWidget
from .models import (
    PointStyle,
    IconStyle,
    PolygonStyle,
    CircleStyle,
    EllipseStyle,
    RasterStyle,
    WMSOptions,
    TileLayerOptions,
    FeatureSelection,
    MeasurementUpdate,
    MapClickEvent,
    VectorVertexEditing,
    LatLon,
    # Fast layers styles
    FastPointsStyle,
    FastGeoPointsStyle,
)

from .layers import (
    FastPointsLayer,
    FastGeoPointsLayer,
)

from .features_table import (
    ColumnSpec,
    ContextMenuActionSpec,
    FeatureTableWidget,
    TableContextMenuEvent,
    TableRowProvider,
)
from .range_slider import RangeSliderWidget
from .time_histogram_slider import TimeHistogramSliderWidget
from .selection_linking import DualSelectLink, MultiSelectLink, TableLink

__all__ = [
    "OLMapWidget",
    "PointStyle",
    "IconStyle",
    "PolygonStyle",
    "CircleStyle",
    "EllipseStyle",
    "RasterStyle",
    "WMSOptions",
    "TileLayerOptions",
    "FeatureSelection",
    "MeasurementUpdate",
    "MapClickEvent",
    "VectorVertexEditing",
    "LatLon",
    # Fast layers styles + layers
    "FastPointsStyle",
    "FastPointsLayer",
    "FastGeoPointsStyle",
    "FastGeoPointsLayer",
    # Reusable Qt widgets
    "ColumnSpec",
    "FeatureTableWidget",
    "ContextMenuActionSpec",
    "TableContextMenuEvent",
    "TableRowProvider",
    "RangeSliderWidget",
    "TimeHistogramSliderWidget",
    "TableLink",
    "DualSelectLink",
    "MultiSelectLink",
    "__version__",
]


def _read_version() -> str:
    """Return the installed package version, falling back to pyproject.toml."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("pyopenlayersqt")
        except PackageNotFoundError:
            pass
    except Exception:
        pass

    try:
        import re
        from pathlib import Path

        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        match = re.search(
            r'^version\s*=\s*["\']([^"\']+)["\']', pyproject.read_text(), re.MULTILINE
        )
        if match:
            return match.group(1)
    except Exception:
        pass
    return "0.0.0"


__version__ = _read_version()
