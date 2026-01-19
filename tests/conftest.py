"""Pytest configuration with lightweight PySide6 and dependency shims.

This conftest runs early to prepare the test runtime environment before importing
modules under test. It creates fake PySide6 packages and stub modules for
pyopenlayersqt.layers and pyopenlayersqt.models with minimal classes/attributes
needed by current code.

These shims live only in test runtime (via sys.modules) and provide minimal
classes/constants required to import modules under test without pulling in
actual PySide6, numpy, matplotlib, or Pillow.
"""

import sys
from dataclasses import dataclass
from typing import Any, Dict, List


# ==============================================================================
# PySide6 shims
# ==============================================================================

class QObject:
    """Minimal QObject stub."""
    pass


class QAbstractTableModel(QObject):
    """Minimal QAbstractTableModel stub."""
    
    def __init__(self, parent=None):
        super().__init__()
        self.parent = parent
    
    def beginResetModel(self):
        pass
    
    def endResetModel(self):
        pass
    
    def beginInsertRows(self, parent, first, last):
        pass
    
    def endInsertRows(self):
        pass


class QModelIndex:
    """Minimal QModelIndex stub."""
    
    def __init__(self, row=-1, column=-1, valid=False):
        self._row = row
        self._column = column
        self._valid = valid
    
    def row(self):
        return self._row
    
    def column(self):
        return self._column
    
    def isValid(self):
        return self._valid


class QtNamespace:
    """Minimal Qt constants namespace."""
    DisplayRole = 0
    ToolTipRole = 3
    ItemIsEnabled = 1
    ItemIsSelectable = 2
    Horizontal = 1
    Vertical = 2
    
    # For ItemFlags
    class ItemFlags:
        def __init__(self, value):
            self.value = value
        
        def __or__(self, other):
            return QtNamespace.ItemFlags(self.value | other.value)


# Make ItemIsEnabled and ItemIsSelectable compatible with flags
QtNamespace.ItemIsEnabled = QtNamespace.ItemFlags(1)
QtNamespace.ItemIsSelectable = QtNamespace.ItemFlags(2)


class Signal:
    """Minimal Signal placeholder."""
    
    def __init__(self, *args):
        self.args = args
    
    def connect(self, slot):
        pass
    
    def disconnect(self, slot=None):
        pass
    
    def emit(self, *args):
        pass


class Slot:
    """Minimal Slot decorator placeholder."""
    
    def __init__(self, *args):
        self.args = args
    
    def __call__(self, func):
        return func


class QUrl:
    """Minimal QUrl stub."""
    
    def __init__(self, url=""):
        self.url = url


class QStandardPaths:
    """Minimal QStandardPaths stub."""
    CacheLocation = 0
    
    @staticmethod
    def writableLocation(location):
        return ""


class QTimer:
    """Minimal QTimer stub."""
    
    def __init__(self, parent=None):
        self.parent = parent
    
    @staticmethod
    def singleShot(ms, callback):
        pass


class QWidget:
    """Minimal QWidget stub."""
    
    def __init__(self, parent=None):
        self.parent = parent


class QHeaderView:
    """Minimal QHeaderView stub."""
    Interactive = 0


class QTableView:
    """Minimal QTableView stub."""
    
    def __init__(self, parent=None):
        self.parent = parent


class QAbstractItemView:
    """Minimal QAbstractItemView stub."""
    SelectRows = 0
    ExtendedSelection = 1


class QVBoxLayout:
    """Minimal QVBoxLayout stub."""
    
    def __init__(self, parent=None):
        self.parent = parent


class QWebChannel:
    """Minimal QWebChannel stub."""
    
    def __init__(self, parent=None):
        self.parent = parent


class QWebEngineView:
    """Minimal QWebEngineView stub."""
    
    def __init__(self, parent=None):
        self.parent = parent


# Create PySide6 module structure
class PySide6Module:
    """Container for PySide6 submodules."""
    pass


class QtCoreModule:
    """PySide6.QtCore shim."""
    QObject = QObject
    QAbstractTableModel = QAbstractTableModel
    QModelIndex = QModelIndex
    Qt = QtNamespace
    Signal = Signal
    Slot = Slot
    QUrl = QUrl
    QStandardPaths = QStandardPaths
    QTimer = QTimer


class QtWidgetsModule:
    """PySide6.QtWidgets shim."""
    QWidget = QWidget
    QHeaderView = QHeaderView
    QTableView = QTableView
    QAbstractItemView = QAbstractItemView
    QVBoxLayout = QVBoxLayout


class QtWebChannelModule:
    """PySide6.QtWebChannel shim."""
    QWebChannel = QWebChannel


class QtWebEngineWidgetsModule:
    """PySide6.QtWebEngineWidgets shim."""
    QWebEngineView = QWebEngineView


# Create PySide6 package
PySide6 = PySide6Module()
PySide6.QtCore = QtCoreModule
PySide6.QtWidgets = QtWidgetsModule
PySide6.QtWebChannel = QtWebChannelModule
PySide6.QtWebEngineWidgets = QtWebEngineWidgetsModule

# Install PySide6 shims into sys.modules
sys.modules['PySide6'] = PySide6
sys.modules['PySide6.QtCore'] = QtCoreModule
sys.modules['PySide6.QtWidgets'] = QtWidgetsModule
sys.modules['PySide6.QtWebChannel'] = QtWebChannelModule
sys.modules['PySide6.QtWebEngineWidgets'] = QtWebEngineWidgetsModule


# ==============================================================================
# pyopenlayersqt.models shims
# ==============================================================================

@dataclass
class FeatureSelection:
    """Stub for FeatureSelection model."""
    layer_id: str = ""
    feature_ids: List[str] = None
    count: int = 0
    raw: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.feature_ids is None:
            self.feature_ids = []
        if self.raw is None:
            self.raw = {}


@dataclass(frozen=True)
class PointStyle:
    """Stub for PointStyle model."""
    radius: float = 5.0
    fill_color: str = "#ff3333"
    fill_opacity: float = 0.85
    stroke_color: str = "#000000"
    stroke_width: float = 1.0
    stroke_opacity: float = 0.9
    
    def to_js(self):
        return {"radius": float(self.radius)}


@dataclass(frozen=True)
class PolygonStyle:
    """Stub for PolygonStyle model."""
    stroke_color: str = "#00aaff"
    stroke_width: float = 2.0
    stroke_opacity: float = 0.95
    fill_color: str = "#00aaff"
    fill_opacity: float = 0.15
    fill: bool = True
    
    def to_js(self):
        return {"stroke_width": float(self.stroke_width)}


@dataclass(frozen=True)
class CircleStyle:
    """Stub for CircleStyle model."""
    stroke_color: str = "#00aaff"
    stroke_width: float = 2.0
    stroke_opacity: float = 0.95
    fill_color: str = "#00aaff"
    fill_opacity: float = 0.15
    fill: bool = True
    
    def to_js(self):
        return {"stroke_width": float(self.stroke_width)}


@dataclass(frozen=True)
class EllipseStyle:
    """Stub for EllipseStyle model."""
    stroke_color: str = "#ffcc00"
    stroke_width: float = 2.0
    stroke_opacity: float = 0.95
    fill_color: str = "#ffcc00"
    fill_opacity: float = 0.12
    fill: bool = True
    
    def to_js(self):
        return {"stroke_width": float(self.stroke_width)}


@dataclass(frozen=True)
class RasterStyle:
    """Stub for RasterStyle model."""
    opacity: float = 0.6
    
    def to_js(self):
        return {"opacity": float(self.opacity)}


@dataclass(frozen=True)
class WMSOptions:
    """Stub for WMSOptions model."""
    url: str = ""
    params: Dict[str, Any] = None
    opacity: float = 1.0
    
    def __post_init__(self):
        if self.params is None:
            object.__setattr__(self, 'params', {})
    
    def to_js(self):
        return {"url": self.url, "params": dict(self.params or {}), "opacity": float(self.opacity)}


@dataclass(frozen=True)
class HeatmapOptions:
    """Stub for HeatmapOptions model."""
    opacity: float = 0.55
    colormap: str = "viridis"
    vmin: float = None
    vmax: float = None


@dataclass(frozen=True)
class FastPointsStyle:
    """Stub for FastPointsStyle model."""
    radius: float = 3.0
    default_rgba: tuple = (255, 51, 51, 204)
    selected_radius: float = 6.0
    selected_rgba: tuple = (0, 255, 255, 255)
    
    def to_js(self):
        return {
            "radius": float(self.radius),
            "default_rgba": list(self.default_rgba),
            "selected_radius": float(self.selected_radius),
            "selected_rgba": list(self.selected_rgba),
        }


@dataclass(frozen=True)
class FastGeoPointsStyle:
    """Stub for FastGeoPointsStyle model."""
    point_radius: float = 3.0
    default_point_rgba: tuple = (255, 51, 51, 204)
    selected_point_radius: float = 6.0
    selected_point_rgba: tuple = (0, 255, 255, 255)
    ellipse_stroke_rgba: tuple = (255, 204, 0, 180)
    ellipse_stroke_width: float = 1.5
    selected_ellipse_stroke_rgba: tuple = None
    selected_ellipse_stroke_width: float = None
    fill_ellipses: bool = False
    ellipse_fill_rgba: tuple = (255, 204, 0, 40)
    ellipses_visible: bool = True
    min_ellipse_px: float = 0.0
    max_ellipses_per_path: int = 2000
    skip_ellipses_while_interacting: bool = True
    
    def to_js(self):
        return {
            "point_radius": float(self.point_radius),
            "default_point_rgba": list(self.default_point_rgba),
            "selected_point_radius": float(self.selected_point_radius),
            "selected_point_rgba": list(self.selected_point_rgba),
            "ellipse_stroke_rgba": list(self.ellipse_stroke_rgba),
            "ellipse_stroke_width": float(self.ellipse_stroke_width),
            "selected_ellipse_stroke_rgba": (list(self.selected_ellipse_stroke_rgba) if self.selected_ellipse_stroke_rgba is not None else None),
            "selected_ellipse_stroke_width": (float(self.selected_ellipse_stroke_width) if self.selected_ellipse_stroke_width is not None else None),
            "fill_ellipses": bool(self.fill_ellipses),
            "ellipse_fill_rgba": list(self.ellipse_fill_rgba),
            "ellipses_visible": bool(self.ellipses_visible),
            "min_ellipse_px": float(self.min_ellipse_px),
            "max_ellipses_per_path": int(self.max_ellipses_per_path),
            "skip_ellipses_while_interacting": bool(self.skip_ellipses_while_interacting),
        }


# Create models module
class ModelsModule:
    """pyopenlayersqt.models shim."""
    FeatureSelection = FeatureSelection
    PointStyle = PointStyle
    PolygonStyle = PolygonStyle
    CircleStyle = CircleStyle
    EllipseStyle = EllipseStyle
    RasterStyle = RasterStyle
    WMSOptions = WMSOptions
    HeatmapOptions = HeatmapOptions
    FastPointsStyle = FastPointsStyle
    FastGeoPointsStyle = FastGeoPointsStyle


# ==============================================================================
# pyopenlayersqt.layers shims
# ==============================================================================

class RasterLayer:
    """Stub for RasterLayer."""
    
    def __init__(self, widget, layer_id, url="", bounds=None, style=None, name=""):
        self._w = widget
        self.id = layer_id
        self.url = url
        self.bounds = bounds or []
        self.style = style
        self.name = name


class VectorLayer:
    """Stub for VectorLayer."""
    
    def __init__(self, widget, layer_id, name=""):
        self._w = widget
        self.id = layer_id
        self.name = name


class WMSLayer:
    """Stub for WMSLayer."""
    
    def __init__(self, widget, layer_id, opt=None, name=""):
        self._w = widget
        self.id = layer_id
        self.opt = opt
        self.name = name


class FastPointsLayer:
    """Stub for FastPointsLayer."""
    
    def __init__(self, widget, layer_id, name=""):
        self._w = widget
        self.id = layer_id
        self.name = name


class FastGeoPointsLayer:
    """Stub for FastGeoPointsLayer."""
    
    def __init__(self, widget, layer_id, name=""):
        self._w = widget
        self.id = layer_id
        self.name = name


# Create layers module
class LayersModule:
    """pyopenlayersqt.layers shim."""
    RasterLayer = RasterLayer
    VectorLayer = VectorLayer
    WMSLayer = WMSLayer
    FastPointsLayer = FastPointsLayer
    FastGeoPointsLayer = FastGeoPointsLayer


# Install pyopenlayersqt shims (but only if they don't exist yet)
if 'pyopenlayersqt.models' not in sys.modules:
    sys.modules['pyopenlayersqt.models'] = ModelsModule

if 'pyopenlayersqt.layers' not in sys.modules:
    sys.modules['pyopenlayersqt.layers'] = LayersModule
