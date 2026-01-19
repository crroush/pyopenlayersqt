"""Test configuration and runtime shims for headless CI.

This conftest.py runs early during pytest collection to prepare the test runtime
environment. It creates minimal shims for PySide6 and heavy dependencies before
any test imports pyopenlayersqt modules.

The shims provide just enough classes/constants to allow imports to succeed
without requiring actual Qt, numpy, matplotlib, or Pillow installations.
"""
import sys
from dataclasses import dataclass
from typing import Any


# ============================================================================
# PySide6 shims
# ============================================================================
class QObject:
    """Minimal QObject stub."""
    pass


class QAbstractTableModel:
    """Minimal QAbstractTableModel stub."""
    def __init__(self, parent=None):
        pass
    
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
    def __init__(self):
        self._valid = False
    
    def isValid(self):
        return self._valid
    
    def row(self):
        return -1
    
    def column(self):
        return -1


class _QtNamespace:
    """Minimal Qt namespace with constants."""
    DisplayRole = 0
    ToolTipRole = 13
    Horizontal = 1
    Vertical = 2
    ItemIsEnabled = 1
    ItemIsSelectable = 2
    ItemFlags = int


class Signal:
    """Minimal Signal stub."""
    def __init__(self, *args):
        pass
    
    def connect(self, slot):
        pass
    
    def disconnect(self, slot=None):
        pass
    
    def emit(self, *args):
        pass


class QWidget:
    """Minimal QWidget stub."""
    def __init__(self, parent=None):
        self.parent = parent


class QHeaderView:
    """Minimal QHeaderView stub."""
    Interactive = 0
    Stretch = 1


class QTableView:
    """Minimal QTableView stub."""
    def __init__(self, parent=None):
        self.parent = parent
    
    def setModel(self, model):
        pass


class QItemSelection:
    """Minimal QItemSelection stub."""
    pass


class QItemSelectionModel:
    """Minimal QItemSelectionModel stub."""
    Select = 0x0002
    Rows = 0x0020


class QAbstractItemView:
    """Minimal QAbstractItemView stub."""
    SelectRows = 0
    ExtendedSelection = 3


class QVBoxLayout:
    """Minimal QVBoxLayout stub."""
    def __init__(self, parent=None):
        pass
    
    def setContentsMargins(self, *args):
        pass
    
    def addWidget(self, widget):
        pass


class QTimer:
    """Minimal QTimer stub."""
    def __init__(self, parent=None):
        pass
    
    def setSingleShot(self, single):
        pass
    
    @property
    def timeout(self):
        return Signal()
    
    def start(self, ms):
        pass


class QUrl:
    """Minimal QUrl stub."""
    def __init__(self, url):
        self.url = url


class QStandardPaths:
    """Minimal QStandardPaths stub."""
    CacheLocation = 0
    
    @staticmethod
    def writableLocation(location):
        return ""


class QWebChannel:
    """Minimal QWebChannel stub."""
    def __init__(self, parent=None):
        pass
    
    def registerObject(self, name, obj):
        pass


class QWebEngineView:
    """Minimal QWebEngineView stub."""
    def __init__(self, parent=None):
        pass
    
    def page(self):
        return self
    
    def setWebChannel(self, channel):
        pass
    
    def setUrl(self, url):
        pass
    
    def runJavaScript(self, script, callback=None):
        pass
    
    @property
    def loadFinished(self):
        return Signal()


def Slot(*args, **kwargs):
    """Minimal Slot decorator stub."""
    def decorator(func):
        return func
    return decorator


# Create PySide6 module structure
pyside6_qtcore = type(sys)('PySide6.QtCore')
pyside6_qtcore.QObject = QObject
pyside6_qtcore.QAbstractTableModel = QAbstractTableModel
pyside6_qtcore.QModelIndex = QModelIndex
pyside6_qtcore.Qt = _QtNamespace()
pyside6_qtcore.Signal = Signal
pyside6_qtcore.Slot = Slot
pyside6_qtcore.QUrl = QUrl
pyside6_qtcore.QStandardPaths = QStandardPaths
pyside6_qtcore.QTimer = QTimer
pyside6_qtcore.QItemSelection = QItemSelection
pyside6_qtcore.QItemSelectionModel = QItemSelectionModel

pyside6_qtwidgets = type(sys)('PySide6.QtWidgets')
pyside6_qtwidgets.QWidget = QWidget
pyside6_qtwidgets.QHeaderView = QHeaderView
pyside6_qtwidgets.QTableView = QTableView
pyside6_qtwidgets.QAbstractItemView = QAbstractItemView
pyside6_qtwidgets.QVBoxLayout = QVBoxLayout

pyside6_qtwebchannel = type(sys)('PySide6.QtWebChannel')
pyside6_qtwebchannel.QWebChannel = QWebChannel

pyside6_qtwebenginewidgets = type(sys)('PySide6.QtWebEngineWidgets')
pyside6_qtwebenginewidgets.QWebEngineView = QWebEngineView

pyside6 = type(sys)('PySide6')
pyside6.QtCore = pyside6_qtcore
pyside6.QtWidgets = pyside6_qtwidgets
pyside6.QtWebChannel = pyside6_qtwebchannel
pyside6.QtWebEngineWidgets = pyside6_qtwebenginewidgets

sys.modules['PySide6'] = pyside6
sys.modules['PySide6.QtCore'] = pyside6_qtcore
sys.modules['PySide6.QtWidgets'] = pyside6_qtwidgets
sys.modules['PySide6.QtWebChannel'] = pyside6_qtwebchannel
sys.modules['PySide6.QtWebEngineWidgets'] = pyside6_qtwebenginewidgets


# ============================================================================
# pyopenlayersqt.models shim
# ============================================================================
@dataclass(frozen=True)
class PointStyle:
    """Stub PointStyle for testing."""
    radius: float = 5.0
    fill_color: str = "#ff3333"
    fill_opacity: float = 0.85
    stroke_color: str = "#000000"
    stroke_width: float = 1.0
    stroke_opacity: float = 0.9
    
    def to_js(self):
        return {"radius": self.radius, "fill": self.fill_color, "stroke": self.stroke_color}


@dataclass(frozen=True)
class PolygonStyle:
    """Stub PolygonStyle for testing."""
    stroke_color: str = "#00aaff"
    stroke_width: float = 2.0
    stroke_opacity: float = 0.95
    fill_color: str = "#00aaff"
    fill_opacity: float = 0.15
    fill: bool = True
    
    def to_js(self):
        return {"stroke": self.stroke_color, "stroke_width": self.stroke_width}


@dataclass(frozen=True)
class CircleStyle:
    """Stub CircleStyle for testing."""
    stroke_color: str = "#00aaff"
    stroke_width: float = 2.0
    stroke_opacity: float = 0.95
    fill_color: str = "#00aaff"
    fill_opacity: float = 0.15
    fill: bool = True
    
    def to_js(self):
        return {"stroke": self.stroke_color, "stroke_width": self.stroke_width}


@dataclass(frozen=True)
class EllipseStyle:
    """Stub EllipseStyle for testing."""
    stroke_color: str = "#ffcc00"
    stroke_width: float = 2.0
    stroke_opacity: float = 0.95
    fill_color: str = "#ffcc00"
    fill_opacity: float = 0.12
    fill: bool = True
    
    def to_js(self):
        return {"stroke": self.stroke_color, "stroke_width": self.stroke_width}


@dataclass(frozen=True)
class RasterStyle:
    """Stub RasterStyle for testing."""
    opacity: float = 0.6
    
    def to_js(self):
        return {"opacity": float(self.opacity)}


@dataclass(frozen=True)
class WMSOptions:
    """Stub WMSOptions for testing."""
    url: str = ""
    params: dict = None
    opacity: float = 1.0
    
    def __post_init__(self):
        if self.params is None:
            object.__setattr__(self, 'params', {})
    
    def to_js(self):
        return {"url": self.url, "params": dict(self.params), "opacity": float(self.opacity)}


@dataclass(frozen=True)
class HeatmapOptions:
    """Stub HeatmapOptions for testing."""
    opacity: float = 0.55
    colormap: str = "viridis"
    vmin: float = None
    vmax: float = None


@dataclass(frozen=True)
class FastPointsStyle:
    """Stub FastPointsStyle for testing."""
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
    """Stub FastGeoPointsStyle for testing."""
    point_radius: float = 3.0
    default_point_rgba: tuple = (255, 51, 51, 204)
    selected_point_radius: float = 6.0
    selected_point_rgba: tuple = (0, 255, 255, 255)
    ellipse_stroke_rgba: tuple = (255, 204, 0, 180)
    ellipse_stroke_width: float = 1.5
    
    def to_js(self):
        return {
            "point_radius": float(self.point_radius),
            "default_point_rgba": list(self.default_point_rgba),
            "selected_point_radius": float(self.selected_point_radius),
            "selected_point_rgba": list(self.selected_point_rgba),
            "ellipse_stroke_rgba": list(self.ellipse_stroke_rgba),
            "ellipse_stroke_width": float(self.ellipse_stroke_width),
        }


@dataclass
class FeatureSelection:
    """Stub FeatureSelection for testing."""
    layer_id: str = ""
    feature_ids: list = None
    count: int = 0
    raw: dict = None
    
    def __post_init__(self):
        if self.feature_ids is None:
            self.feature_ids = []
        if self.raw is None:
            self.raw = {}


# Create pyopenlayersqt.models module
pyol_models = type(sys)('pyopenlayersqt.models')
pyol_models.PointStyle = PointStyle
pyol_models.PolygonStyle = PolygonStyle
pyol_models.CircleStyle = CircleStyle
pyol_models.EllipseStyle = EllipseStyle
pyol_models.RasterStyle = RasterStyle
pyol_models.WMSOptions = WMSOptions
pyol_models.HeatmapOptions = HeatmapOptions
pyol_models.FastPointsStyle = FastPointsStyle
pyol_models.FastGeoPointsStyle = FastGeoPointsStyle
pyol_models.FeatureSelection = FeatureSelection

sys.modules['pyopenlayersqt.models'] = pyol_models


# ============================================================================
# pyopenlayersqt.layers shim
# ============================================================================
class RasterLayer:
    """Stub RasterLayer for testing."""
    def __init__(self, widget, layer_id, url="", bounds=None, style=None, name=""):
        self.id = layer_id
        self.name = name


class VectorLayer:
    """Stub VectorLayer for testing."""
    def __init__(self, widget, layer_id, name=""):
        self.id = layer_id
        self.name = name


class WMSLayer:
    """Stub WMSLayer for testing."""
    def __init__(self, widget, layer_id, opt=None, name=""):
        self.id = layer_id
        self.name = name


class FastPointsLayer:
    """Stub FastPointsLayer for testing."""
    def __init__(self, map_widget, layer_id, name=""):
        self.id = layer_id
        self.name = name


class FastGeoPointsLayer:
    """Stub FastGeoPointsLayer for testing."""
    def __init__(self, map_widget, layer_id, name=""):
        self.id = layer_id
        self.name = name


# Create pyopenlayersqt.layers module
pyol_layers = type(sys)('pyopenlayersqt.layers')
pyol_layers.RasterLayer = RasterLayer
pyol_layers.VectorLayer = VectorLayer
pyol_layers.WMSLayer = WMSLayer
pyol_layers.FastPointsLayer = FastPointsLayer
pyol_layers.FastGeoPointsLayer = FastGeoPointsLayer

sys.modules['pyopenlayersqt.layers'] = pyol_layers
