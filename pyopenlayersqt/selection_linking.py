"""Helpers for syncing map selections with one parent table and many child tables."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from functools import partial
from typing import Callable, Mapping, Sequence

from PySide6.QtCore import QSignalBlocker

from .features_table import FeatureTableWidget
from .layers import BaseLayer, FastGeoPointsLayer, FastPointsLayer, VectorLayer
from .widget import OLMapWidget

SetSel = Callable[[str, list[str]], None]


@dataclass(frozen=True)
class TableLink:
    """Link one map layer to one table widget."""

    table: FeatureTableWidget
    layer: BaseLayer

    @property
    def lid(self) -> str:
        return self.layer.id

    def keys(self, ids: Sequence[str]) -> list[tuple[str, str]]:
        return [(self.layer.id, fid) for fid in ids]


class MultiSelectLink:
    """Sync one parent layer/table with many child layer/table links."""

    def __init__(
        self,
        *,
        map_widget: OLMapWidget,
        parent: TableLink,
        kids: Mapping[str, TableLink],
        parent_by_kid: Mapping[str, Mapping[str, str]],
        clear_parent_on_kid_subset: bool = True,
    ) -> None:
        self.map_widget = map_widget
        self.parent = parent
        self.kids = dict(kids)
        self.clear_parent_on_kid_subset = bool(clear_parent_on_kid_subset)

        self.kid_by_lid: dict[str, str] = {
            link.lid: kid_name for kid_name, link in self.kids.items()
        }

        self.parent_by_kid: dict[str, dict[str, str]] = {}
        self.kid_by_parent: dict[str, dict[str, list[str]]] = {}
        MultiSelectLink.set_links(self, parent_by_kid)

        self.parent_sel: set[str] = set()
        self.kid_sel: dict[str, set[str]] = {kid_name: set() for kid_name in self.kids}
        self._from_map = False

        self.map_widget.selectionChanged.connect(self._on_map)
        self.parent.table.selectionKeysChanged.connect(self._on_parent_table)
        for kid_name, link in self.kids.items():
            link.table.selectionKeysChanged.connect(partial(self._on_kid_table, kid_name))

    def set_links(self, parent_by_kid: Mapping[str, Mapping[str, str]]) -> None:
        """Replace parent/child ownership mappings for one or more child links."""
        self.parent_by_kid = {}
        self.kid_by_parent = {}

        for kid_name, raw in parent_by_kid.items():
            if kid_name not in self.kids:
                continue
            mapping = {
                str(kid_id): str(parent_id)
                for kid_id, parent_id in raw.items()
            }
            grouped: dict[str, list[str]] = defaultdict(list)
            for kid_id, parent_id in mapping.items():
                grouped[parent_id].append(kid_id)
            self.parent_by_kid[kid_name] = mapping
            self.kid_by_parent[kid_name] = dict(grouped)

        for kid_name in self.kids:
            self.parent_by_kid.setdefault(kid_name, {})
            self.kid_by_parent.setdefault(kid_name, {})

    def set_parent(self, parent_ids: Sequence[str], *, set_map: bool = True) -> None:
        pids = list(dict.fromkeys(str(pid) for pid in parent_ids))
        self.parent_sel = set(pids)

        self.parent.table.select_keys(self.parent.keys(pids), clear_first=True)
        if set_map:
            self._set_map(self.parent, pids)

        for kid_name, link in self.kids.items():
            kid_ids = [
                kid_id
                for pid in pids
                for kid_id in self.kid_by_parent[kid_name].get(pid, [])
            ]
            self.kid_sel[kid_name] = set(kid_ids)
            link.table.select_keys(link.keys(kid_ids), clear_first=True)
            self._set_map(link, kid_ids)

    def set_kid(
        self,
        kid_name: str,
        kid_ids: Sequence[str],
        *,
        set_map: bool = True,
        clear_parent: bool = False,
    ) -> None:
        if kid_name not in self.kids:
            return

        link = self.kids[kid_name]
        ids = list(dict.fromkeys(str(kid_id) for kid_id in kid_ids))
        self.kid_sel[kid_name] = set(ids)

        link.table.select_keys(link.keys(ids), clear_first=True)
        if set_map:
            self._set_map(link, ids)

        if clear_parent:
            self.parent_sel.clear()
            self.parent.table.clear_selection()
            self._set_map(self.parent, [])

    def _expected_kid(self, kid_name: str) -> set[str]:
        return {
            kid_id
            for pid in self.parent_sel
            for kid_id in self.kid_by_parent[kid_name].get(pid, [])
        }

    def _on_parent_table(self, keys: list[tuple[str, str]]) -> None:
        if self._from_map:
            return
        self.set_parent([fid for _lid, fid in keys])

    def _on_kid_table(self, kid_name: str, keys: list[tuple[str, str]]) -> None:
        if self._from_map:
            return
        self.set_kid(kid_name, [fid for _lid, fid in keys], clear_parent=False)

    def _on_map(self, sel) -> None:
        self._from_map = True
        try:
            if sel.layer_id == self.parent.lid:
                self.set_parent(list(sel.feature_ids), set_map=False)
                return

            kid_name = self.kid_by_lid.get(sel.layer_id)
            if kid_name is None:
                return

            incoming = set(sel.feature_ids)
            if self.parent_sel and incoming == self._expected_kid(kid_name):
                self.kid_sel[kid_name] = incoming
                return

            self.set_kid(
                kid_name,
                list(sel.feature_ids),
                set_map=False,
                clear_parent=self.clear_parent_on_kid_subset,
            )
        finally:
            self._from_map = False

    def _set_map(self, link: TableLink, ids: list[str]) -> None:
        blocker = QSignalBlocker(self.map_widget)
        setter = self._pick_setter(link.layer)
        setter(link.lid, ids)
        del blocker

    def _pick_setter(self, layer: BaseLayer) -> SetSel:
        if isinstance(layer, VectorLayer):
            return self.map_widget.set_vector_selection
        if isinstance(layer, FastPointsLayer):
            return self.map_widget.set_fast_points_selection
        if isinstance(layer, FastGeoPointsLayer):
            return self.map_widget.set_fast_geopoints_selection
        raise TypeError(f"Unsupported layer type: {type(layer).__name__}")


class DualSelectLink(MultiSelectLink):
    """Thin wrapper for the common one-child case."""

    def __init__(
        self,
        *,
        map_widget: OLMapWidget,
        parent: TableLink,
        child: TableLink,
        parent_by_child: Mapping[str, str],
        clear_parent_on_child_subset: bool = True,
    ) -> None:
        super().__init__(
            map_widget=map_widget,
            parent=parent,
            kids={"child": child},
            parent_by_kid={"child": parent_by_child},
            clear_parent_on_kid_subset=clear_parent_on_child_subset,
        )

    def set_links(
        self,
        parent_by_kid: Mapping[str, Mapping[str, str]] | Mapping[str, str],
    ) -> None:
        """Set child mapping using either wrapped or one-child shorthand input."""
        values = list(parent_by_kid.values())
        is_wrapped = bool(values) and all(hasattr(v, "items") for v in values)
        if is_wrapped:
            super().set_links(parent_by_kid)  # type: ignore[arg-type]
            return
        super().set_links({"child": parent_by_kid})  # type: ignore[arg-type]

    def set_child(
        self,
        child_ids: Sequence[str],
        *,
        set_map: bool = True,
        clear_parent: bool = False,
    ) -> None:
        super().set_kid(
            "child",
            child_ids,
            set_map=set_map,
            clear_parent=clear_parent,
        )
