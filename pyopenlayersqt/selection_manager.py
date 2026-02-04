"""High-performance bidirectional selection manager for map-table sync.

This module provides a SelectionManager that coordinates selection between:
  - Map features (across multiple layers)
  - Multiple feature tables
  - Custom selection behaviors and linking patterns

Designed to handle 100K+ features efficiently with minimal lag.

Key Features:
  - Bidirectional sync (map ↔ table, table ↔ table)
  - Configurable selection strategies (1-to-1, 1-to-many, many-to-many)
  - Batched selection updates for performance
  - Optional selection modes (bidirectional, map-only, table-only)
  - Builder pattern for easy configuration

Example usage:

    # Simple 1-to-1 selection between map and table using builder
    builder = SelectionManagerBuilder()
    builder.set_map_widget(map_widget)
    builder.add_table_layer_link(table, layer_id="points")
    manager = builder.build()
    
    # Cross-table selection with custom mapping
    builder = SelectionManagerBuilder()
    builder.set_map_widget(map_widget)
    builder.add_table_layer_link(table1, layer_id="points")
    builder.add_table_table_link(
        table1, table2,
        key_mapper=lambda keys: expand_to_related_keys(keys)
    )
    manager = builder.build()
    
    # Performance monitoring
    builder.enable_performance_stats()
    manager = builder.build()
    stats = manager.get_stats()  # Track selection update times
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

from PySide6 import QtCore

# Type aliases
FeatureKey = Tuple[str, str]  # (layer_id, feature_id)
KeyMapper = Callable[[List[FeatureKey]], List[FeatureKey]]


@dataclass
class SelectionStats:
    """Performance statistics for selection operations."""
    
    total_updates: int = 0
    total_time_ms: float = 0.0
    max_time_ms: float = 0.0
    min_time_ms: float = float('inf')
    avg_time_ms: float = 0.0
    last_update_ms: float = 0.0
    last_item_count: int = 0
    
    def record_update(self, duration_ms: float, item_count: int) -> None:
        """Record a selection update operation."""
        self.total_updates += 1
        self.total_time_ms += duration_ms
        self.max_time_ms = max(self.max_time_ms, duration_ms)
        self.min_time_ms = min(self.min_time_ms, duration_ms)
        self.avg_time_ms = self.total_time_ms / self.total_updates
        self.last_update_ms = duration_ms
        self.last_item_count = item_count


@dataclass
class SelectionLink:
    """Defines a selection link between a table and layer/other table."""
    
    source_id: str
    target_id: str
    key_mapper: Optional[KeyMapper] = None
    bidirectional: bool = True
    enabled: bool = True
    
    def map_keys(self, keys: List[FeatureKey]) -> List[FeatureKey]:
        """Transform keys using the mapper if defined."""
        if self.key_mapper is None:
            return keys
        return self.key_mapper(keys)


class SelectionManager(QtCore.QObject):
    """Manages bidirectional selection between map layers and feature tables.
    
    Coordinates selection across multiple tables and map layers with configurable
    linking behavior. Optimized for handling 100K+ features.
    
    Signals:
        selectionChanged: Emitted when selection changes (source_id, keys)
    """
    
    selectionChanged = QtCore.Signal(str, list)
    
    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        
        # Track all registered components
        self._tables: Dict[str, Any] = {}  # table_id -> FeatureTableWidget
        self._layers: Dict[str, Any] = {}  # layer_id -> Layer object
        self._map_widget: Optional[Any] = None
        
        # Selection links: source_id -> [SelectionLink]
        self._links: Dict[str, List[SelectionLink]] = {}
        
        # Current selections: component_id -> Set[FeatureKey]
        self._selections: Dict[str, Set[FeatureKey]] = {}
        
        # Prevent circular updates
        self._updating = False
        
        # Performance tracking
        self._stats_enabled = False
        self._stats = SelectionStats()
        
        # Debounce timer for batched updates
        self._update_timer = QtCore.QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._process_pending_updates)
        self._pending_updates: Dict[str, List[FeatureKey]] = {}
        self._debounce_ms = 50
    
    def enable_performance_stats(self, enabled: bool = True) -> None:
        """Enable or disable performance statistics tracking."""
        self._stats_enabled = enabled
        if not enabled:
            self._stats = SelectionStats()
    
    def get_stats(self) -> SelectionStats:
        """Get current performance statistics."""
        return self._stats
    
    def set_debounce_ms(self, ms: int) -> None:
        """Set debounce time for batched selection updates."""
        self._debounce_ms = max(0, ms)
    
    def register_table(
        self,
        table: Any,
        table_id: Optional[str] = None,
    ) -> str:
        """Register a feature table with the manager.
        
        Args:
            table: FeatureTableWidget instance
            table_id: Unique identifier (auto-generated if not provided)
            
        Returns:
            The table_id used for registration
        """
        if table_id is None:
            table_id = f"table_{id(table)}"
        
        # Check if already registered
        if table_id in self._tables:
            return table_id
        
        self._tables[table_id] = table
        self._selections[table_id] = set()
        
        # Connect to table's selection signal
        table.selectionKeysChanged.connect(
            lambda keys: self._on_table_selection_changed(table_id, keys)
        )
        
        return table_id
    
    def register_map_widget(self, map_widget: Any) -> None:
        """Register the map widget with the manager.
        
        Args:
            map_widget: OLMapWidget instance
        """
        self._map_widget = map_widget
        
        # Connect to map selection signal
        map_widget.selectionChanged.connect(self._on_map_selection_changed)
    
    def register_layer(self, layer: Any, layer_id: Optional[str] = None) -> str:
        """Register a map layer with the manager.
        
        Args:
            layer: Layer instance (VectorLayer, FastPointsLayer, etc.)
            layer_id: Layer identifier (uses layer.id if not provided)
            
        Returns:
            The layer_id used for registration
        """
        if layer_id is None:
            layer_id = getattr(layer, 'id', f"layer_{id(layer)}")
        
        self._layers[layer_id] = layer
        self._selections[layer_id] = set()
        
        return layer_id
    
    def link_table_to_layer(
        self,
        table: Any,
        layer_id: str,
        table_id: Optional[str] = None,
        key_mapper: Optional[KeyMapper] = None,
        bidirectional: bool = True,
    ) -> str:
        """Link a table to a map layer for synchronized selection.
        
        Args:
            table: FeatureTableWidget instance
            layer_id: ID of the layer to link to
            table_id: Unique table identifier (auto-generated if not provided)
            key_mapper: Optional function to transform keys (table keys -> layer keys)
            bidirectional: If True, selection syncs both ways; if False, only table->layer
            
        Returns:
            The table_id used for registration
        """
        tid = self.register_table(table, table_id)
        
        # Create link from table to layer
        if tid not in self._links:
            self._links[tid] = []
        
        self._links[tid].append(SelectionLink(
            source_id=tid,
            target_id=layer_id,
            key_mapper=key_mapper,
            bidirectional=bidirectional,
        ))
        
        # Create reverse link if bidirectional
        if bidirectional:
            if layer_id not in self._links:
                self._links[layer_id] = []
            
            # Reverse mapper (if any)
            reverse_mapper = None
            if key_mapper is not None:
                # For simple cases, reverse is identity; user can provide custom if needed
                reverse_mapper = None
            
            self._links[layer_id].append(SelectionLink(
                source_id=layer_id,
                target_id=tid,
                key_mapper=reverse_mapper,
                bidirectional=False,  # Already handled by forward link
            ))
        
        return tid
    
    def link_tables(
        self,
        table1: Any,
        table2: Any,
        table1_id: Optional[str] = None,
        table2_id: Optional[str] = None,
        key_mapper: Optional[KeyMapper] = None,
        bidirectional: bool = True,
    ) -> Tuple[str, str]:
        """Link two tables for synchronized selection (e.g., parent-child relationships).
        
        Args:
            table1: First FeatureTableWidget
            table2: Second FeatureTableWidget
            table1_id: Unique ID for table1
            table2_id: Unique ID for table2
            key_mapper: Transform keys from table1 to table2 (e.g., expand to children)
            bidirectional: If True, selection syncs both ways
            
        Returns:
            Tuple of (table1_id, table2_id) used for registration
        """
        t1_id = self.register_table(table1, table1_id)
        t2_id = self.register_table(table2, table2_id)
        
        # Create link from table1 to table2
        if t1_id not in self._links:
            self._links[t1_id] = []
        
        self._links[t1_id].append(SelectionLink(
            source_id=t1_id,
            target_id=t2_id,
            key_mapper=key_mapper,
            bidirectional=bidirectional,
        ))
        
        # Create reverse link if bidirectional
        if bidirectional:
            if t2_id not in self._links:
                self._links[t2_id] = []
            
            self._links[t2_id].append(SelectionLink(
                source_id=t2_id,
                target_id=t1_id,
                key_mapper=None,  # Could provide reverse mapper if needed
                bidirectional=False,
            ))
        
        return (t1_id, t2_id)
    
    def set_link_enabled(self, source_id: str, target_id: str, enabled: bool) -> None:
        """Enable or disable a specific selection link.
        
        Args:
            source_id: Source component ID
            target_id: Target component ID
            enabled: Whether the link should be active
        """
        if source_id in self._links:
            for link in self._links[source_id]:
                if link.target_id == target_id:
                    link.enabled = enabled
    
    def clear_all_selections(self) -> None:
        """Clear selections across all registered components."""
        if self._updating:
            return
        
        self._updating = True
        try:
            # Clear table selections
            for table in self._tables.values():
                table.clear_selection()
            
            # Clear map selections
            if self._map_widget is not None:
                for layer_id in self._layers:
                    self._map_widget.clear_selection(layer_id)
            
            # Clear internal state
            for key in self._selections:
                self._selections[key] = set()
        
        finally:
            self._updating = False
    
    def _on_table_selection_changed(self, table_id: str, keys: List[FeatureKey]) -> None:
        """Handle selection change from a table."""
        if self._updating:
            return
        
        # Update internal state
        self._selections[table_id] = set(keys)
        
        # Emit signal
        self.selectionChanged.emit(table_id, keys)
        
        # Propagate to linked components
        self._propagate_selection(table_id, keys)
    
    def _on_map_selection_changed(self, selection: Any) -> None:
        """Handle selection change from the map.
        
        Args:
            selection: FeatureSelection object with layer_id and feature_ids
        """
        if self._updating:
            return
        
        layer_id = selection.layer_id
        feature_ids = selection.feature_ids
        
        # Convert to FeatureKey format (layer_id, feature_id)
        keys = [(layer_id, fid) for fid in feature_ids]
        
        # Update internal state
        if layer_id in self._selections:
            self._selections[layer_id] = set(keys)
        
        # Emit signal
        self.selectionChanged.emit(layer_id, keys)
        
        # Propagate to linked components
        self._propagate_selection(layer_id, keys)
    
    def _propagate_selection(self, source_id: str, keys: List[FeatureKey]) -> None:
        """Propagate selection from source to all linked targets.
        
        Args:
            source_id: ID of the component where selection originated
            keys: Selected feature keys
        """
        start_time = time.perf_counter() if self._stats_enabled else 0
        
        if source_id not in self._links:
            return
        
        # Collect all updates to apply
        updates: Dict[str, List[FeatureKey]] = {}
        
        for link in self._links[source_id]:
            if not link.enabled:
                continue
            
            target_id = link.target_id
            
            # Transform keys if mapper is defined
            target_keys = link.map_keys(keys)
            
            # Accumulate updates
            if target_id not in updates:
                updates[target_id] = []
            updates[target_id].extend(target_keys)
        
        # Apply updates
        if updates:
            self._pending_updates.update(updates)
            self._update_timer.start(self._debounce_ms)
        
        if self._stats_enabled:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._stats.record_update(duration_ms, len(keys))
    
    def _process_pending_updates(self) -> None:
        """Process batched selection updates."""
        if not self._pending_updates:
            return
        
        self._updating = True
        try:
            for target_id, keys in self._pending_updates.items():
                # Remove duplicates
                unique_keys = list(set(keys))
                
                if target_id in self._tables:
                    # Update table selection
                    table = self._tables[target_id]
                    table.select_keys(unique_keys, clear_first=True)
                
                elif target_id in self._layers and self._map_widget is not None:
                    # Update map layer selection
                    # Extract feature IDs for this layer
                    feature_ids = [fid for lid, fid in unique_keys if lid == target_id]
                    if feature_ids:
                        self._map_widget.set_selection(target_id, feature_ids)
        
        finally:
            self._pending_updates.clear()
            self._updating = False


class SelectionManagerBuilder:
    """Builder for easy SelectionManager configuration.
    
    Example:
        builder = SelectionManagerBuilder()
        builder.add_table_layer_link(points_table, "points_layer")
        builder.add_table_layer_link(polygons_table, "polygons_layer")
        manager = builder.build()
    """
    
    def __init__(self) -> None:
        self._manager = SelectionManager()
        self._map_widget: Optional[Any] = None
    
    def set_map_widget(self, map_widget: Any) -> SelectionManagerBuilder:
        """Set the map widget."""
        self._map_widget = map_widget
        return self
    
    def add_table_layer_link(
        self,
        table: Any,
        layer_id: str,
        table_id: Optional[str] = None,
        bidirectional: bool = True,
        key_mapper: Optional[KeyMapper] = None,
    ) -> SelectionManagerBuilder:
        """Add a table-to-layer link."""
        self._manager.link_table_to_layer(
            table, layer_id, table_id, key_mapper, bidirectional
        )
        return self
    
    def add_table_table_link(
        self,
        table1: Any,
        table2: Any,
        table1_id: Optional[str] = None,
        table2_id: Optional[str] = None,
        bidirectional: bool = True,
        key_mapper: Optional[KeyMapper] = None,
    ) -> SelectionManagerBuilder:
        """Add a table-to-table link."""
        self._manager.link_tables(
            table1, table2,
            table1_id=table1_id,
            table2_id=table2_id,
            bidirectional=bidirectional,
            key_mapper=key_mapper,
        )
        return self
    
    def enable_performance_stats(self) -> SelectionManagerBuilder:
        """Enable performance tracking."""
        self._manager.enable_performance_stats(True)
        return self
    
    def set_debounce_ms(self, ms: int) -> SelectionManagerBuilder:
        """Set debounce time for updates."""
        self._manager.set_debounce_ms(ms)
        return self
    
    def build(self) -> SelectionManager:
        """Build and return the configured SelectionManager."""
        if self._map_widget is not None:
            self._manager.register_map_widget(self._map_widget)
        return self._manager
