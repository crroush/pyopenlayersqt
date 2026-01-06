from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class BaseLayer:
    widget: Any
    name: str

    def remove(self) -> None:
        self.widget.remove_layer(self.name)

    def set_visible(self, visible: bool) -> None:
        self.widget.set_visible(self.name, visible)

    def set_opacity(self, opacity: float) -> None:
        self.widget.set_opacity(self.name, opacity)


@dataclass
class VectorLayer(BaseLayer):
    pass


@dataclass
class WMSLayer(BaseLayer):
    pass


@dataclass
class RasterLayer(BaseLayer):
    url: Optional[str] = None
    extent_lonlat: Optional[tuple[float, float, float, float]] = None
