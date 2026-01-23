#!/usr/bin/env python3
"""Background Worker with Responsive GUI Example

This example demonstrates responsive GUI behavior during long-running computations:
- Uses `watch_view_extent` to observe map extent changes
- Offloads heavy computation to background worker (QRunnable/QThreadPool)
- Implements cancel/interrupt mechanism (generation token + cancel flag)
- Updates map layer only when the latest computation finishes
- GUI remains responsive during long-running polygon/heatmap computations

Key Pattern:
1. Each extent change triggers a new computation with a unique generation token
2. Previous computation is marked as cancelled (won't update UI when complete)
3. Worker checks cancel flag periodically during computation
4. Results are applied to map only if the generation token matches current
5. This prevents stale results from updating the UI

This pattern is essential for:
- Dynamic data loading based on map extent
- Real-time heatmap/polygon generation
- Any heavy computation that should respond to rapid user interactions
"""

import io
import sys
import time
from typing import Optional

import numpy as np
from PIL import Image
from matplotlib import colormaps
from matplotlib import colors as mcolors
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject

from pyopenlayersqt import OLMapWidget, RasterStyle, VectorLayer, PolygonStyle


class WorkerSignals(QObject):
    """Signals for background worker to communicate with main thread."""
    finished = Signal(int, bytes, list)  # generation, png_bytes, bounds
    error = Signal(int, str)  # generation, error_message
    progress = Signal(int, str)  # generation, status_message


class HeatmapWorker(QRunnable):
    """Background worker for heavy heatmap computation.
    
    Key features:
    - Runs in QThreadPool to keep GUI responsive
    - Checks cancel flag periodically during computation
    - Emits results with generation token to prevent stale updates
    """
    
    def __init__(self, extent: dict, generation: int, n_points: int = 500, grid_size: int = 512):
        super().__init__()
        self.extent = extent
        self.generation = generation
        self.n_points = n_points
        self.grid_size = grid_size
        self.cancelled = False
        self.signals = WorkerSignals()
    
    def cancel(self):
        """Mark this worker as cancelled. It will stop processing and not emit results."""
        self.cancelled = True
    
    def run(self):
        """Execute the heavy computation in background thread."""
        try:
            # Simulate checking cancel flag before starting
            if self.cancelled:
                return
            
            self.signals.progress.emit(self.generation, "Generating random points...")
            
            # Generate random points within extent
            lon_min = float(self.extent["lon_min"])
            lon_max = float(self.extent["lon_max"])
            lat_min = float(self.extent["lat_min"])
            lat_max = float(self.extent["lat_max"])
            
            rng = np.random.default_rng(self.generation)
            lons = lon_min + (lon_max - lon_min) * rng.random(self.n_points)
            lats = lat_min + (lat_max - lat_min) * rng.random(self.n_points)
            values = rng.random(self.n_points)
            
            # Check cancel flag after point generation
            if self.cancelled:
                return
            
            self.signals.progress.emit(self.generation, "Computing heatmap grid...")
            
            # Create grid for heatmap
            gx = np.linspace(lon_min, lon_max, self.grid_size)
            gy = np.linspace(lat_min, lat_max, self.grid_size)
            grid_lon, grid_lat = np.meshgrid(gx, gy)
            
            # Simulate heavy computation with IDW (Inverse Distance Weighting)
            # This is the computation-heavy part where cancellation is important
            eps = 1e-12
            z = np.zeros((self.grid_size, self.grid_size), dtype=np.float64)
            
            # Process in chunks to allow periodic cancel checks
            chunk_size = max(1, self.grid_size // 10)
            for i in range(0, self.grid_size, chunk_size):
                if self.cancelled:
                    return
                
                end_i = min(i + chunk_size, self.grid_size)
                chunk_lat = grid_lat[i:end_i, :]
                chunk_lon = grid_lon[i:end_i, :]
                
                # Compute distances from each grid point to all data points
                d2 = (
                    (chunk_lon[..., None] - lons[None, None, :]) ** 2
                    + (chunk_lat[..., None] - lats[None, None, :]) ** 2
                    + eps
                )
                w = 1.0 / d2
                z[i:end_i, :] = (w * values[None, None, :]).sum(axis=2) / w.sum(axis=2)
                
                # Simulate additional processing time to make cancellation more visible
                time.sleep(0.05)
            
            # Check one more time before rendering
            if self.cancelled:
                return
            
            self.signals.progress.emit(self.generation, "Rendering PNG...")
            
            # Apply colormap
            vmin = float(np.percentile(z, 2))
            vmax = float(np.percentile(z, 98))
            norm = mcolors.Normalize(vmin=vmin, vmax=vmax, clip=True)
            cmap = colormaps.get_cmap("viridis")
            rgba = (cmap(norm(z), bytes=True)).astype(np.uint8)
            
            # Convert to PNG bytes
            img = Image.fromarray(rgba, mode="RGBA")
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            png_bytes = buf.getvalue()
            
            # Define bounds for raster overlay
            bounds = [
                (lat_min, lon_min),  # Southwest corner
                (lat_max, lon_max)   # Northeast corner
            ]
            
            # Final cancel check before emitting results
            if self.cancelled:
                return
            
            # Emit finished signal with generation token
            # Main thread will check if this generation is still current
            self.signals.finished.emit(self.generation, png_bytes, bounds)
            
        except Exception as e:
            if not self.cancelled:
                self.signals.error.emit(self.generation, str(e))


class BackgroundWorkerWindow(QtWidgets.QMainWindow):
    """Main window demonstrating background worker pattern with cancellation."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Background Worker Heatmap Example - pyopenlayersqt")
        self.resize(1400, 900)
        
        # Thread pool for background workers
        self.thread_pool = QThreadPool.globalInstance()
        print(f"Using thread pool with max {self.thread_pool.maxThreadCount()} threads")
        
        # Generation token for cancellation
        # Each extent change increments this, invalidating previous workers
        self.current_generation = 0
        
        # Track active worker to cancel it when extent changes
        self.active_worker: Optional[HeatmapWorker] = None
        
        # Raster layer for heatmap overlay
        self.raster_layer = None
        
        # Vector layer for extent visualization
        self.vector_layer = None
        
        # Create map widget centered on US
        self.map_widget = OLMapWidget(center=(37.0, -95.0), zoom=4)
        
        # Status label
        self.status_label = QtWidgets.QLabel("Pan/zoom the map to start heatmap generation...")
        self.status_label.setStyleSheet("padding: 8px; background-color: #f0f0f0;")
        
        # Info panel
        info_panel = self._create_info_panel()
        
        # Layout
        central_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central_widget)
        layout.addWidget(info_panel)
        layout.addWidget(self.map_widget, 1)
        layout.addWidget(self.status_label)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(central_widget)
        
        # Setup extent watching after map is ready
        self.map_widget.ready.connect(self.on_map_ready)
    
    def _create_info_panel(self) -> QtWidgets.QWidget:
        """Create info panel explaining the example."""
        panel = QtWidgets.QWidget()
        panel.setStyleSheet("background-color: #e8f4f8; padding: 12px;")
        
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(12, 8, 12, 8)
        
        title = QtWidgets.QLabel("🔄 Responsive GUI with Background Workers")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #0066cc;")
        
        desc = QtWidgets.QLabel(
            "This example demonstrates how to keep the GUI responsive during heavy computations:\n"
            "• Pan/zoom the map rapidly - each change triggers a new computation\n"
            "• Old computations are cancelled automatically (won't update the map)\n"
            "• Only the latest computation updates the heatmap overlay\n"
            "• GUI remains responsive even during heavy processing"
        )
        desc.setWordWrap(True)
        
        layout.addWidget(title)
        layout.addWidget(desc)
        
        return panel
    
    def on_map_ready(self):
        """Setup extent watching when map is ready."""
        self.status_label.setText("Map ready. Watching for extent changes...")
        
        # Add vector layer for debugging extent bounds (optional)
        self.vector_layer = self.map_widget.add_vector_layer("extent_bounds", selectable=False)
        
        # Watch for extent changes with debouncing
        # debounce_ms controls how long to wait after user stops panning/zooming
        # before triggering computation (150ms is a good balance)
        self.extent_watch_handle = self.map_widget.watch_view_extent(
            self.on_extent_changed,
            debounce_ms=150
        )
        
        print("Started watching map extent changes")
    
    def on_extent_changed(self, extent: dict):
        """Handle map extent change - trigger new background computation.
        
        This is the key pattern:
        1. Cancel any previous worker
        2. Increment generation token
        3. Start new worker with current generation
        4. Worker will only update UI if generation still matches
        """
        # Increment generation to invalidate previous workers
        self.current_generation += 1
        generation = self.current_generation
        
        print(f"\n=== Extent changed (generation {generation}) ===")
        print(f"Extent: lat [{extent['lat_min']:.2f}, {extent['lat_max']:.2f}], "
              f"lon [{extent['lon_min']:.2f}, {extent['lon_max']:.2f}], "
              f"zoom {extent['zoom']}")
        
        # Cancel previous worker if still running
        if self.active_worker is not None:
            print(f"Cancelling previous worker (generation {generation - 1})")
            self.active_worker.cancel()
            self.active_worker = None
        
        self.status_label.setText(
            f"🔄 Generation {generation}: Starting heatmap computation..."
        )
        
        # Create and start new worker
        worker = HeatmapWorker(
            extent=extent,
            generation=generation,
            n_points=500,  # More points = heavier computation
            grid_size=512  # Larger grid = heavier computation
        )
        
        # Connect signals
        worker.signals.finished.connect(self.on_worker_finished)
        worker.signals.error.connect(self.on_worker_error)
        worker.signals.progress.connect(self.on_worker_progress)
        
        # Store reference to cancel if needed
        self.active_worker = worker
        
        # Start worker in thread pool
        self.thread_pool.start(worker)
        print(f"Started worker in background thread pool")
    
    def on_worker_progress(self, generation: int, message: str):
        """Handle progress updates from worker (runs in main thread)."""
        # Only show progress if this is still the current generation
        if generation == self.current_generation:
            self.status_label.setText(f"🔄 Generation {generation}: {message}")
            print(f"  Progress (gen {generation}): {message}")
        else:
            print(f"  Ignoring progress from stale generation {generation}")
    
    def on_worker_finished(self, generation: int, png_bytes: bytes, bounds: list):
        """Handle worker completion (runs in main thread).
        
        This is called when worker finishes, but we only update the UI
        if the generation token matches current (i.e., no newer computation started).
        """
        print(f"Worker finished (generation {generation}), "
              f"current generation is {self.current_generation}")
        
        # Check if this result is still current
        if generation != self.current_generation:
            print(f"  ⚠️  Ignoring stale result from generation {generation}")
            self.status_label.setText(
                f"⚠️  Ignored stale result (generation {generation}, current {self.current_generation})"
            )
            return
        
        # This is the latest result - update the map!
        print(f"  ✅ Applying result from generation {generation}")
        
        # Remove old raster layer if exists
        if self.raster_layer is not None:
            self.raster_layer.remove()
        
        # Add new heatmap overlay
        self.raster_layer = self.map_widget.add_raster_image(
            png_bytes,
            bounds=bounds,
            style=RasterStyle(opacity=0.7),
            name="heatmap"
        )
        
        self.status_label.setText(
            f"✅ Generation {generation}: Heatmap updated successfully! "
            f"({len(png_bytes) // 1024} KB)"
        )
        
        # Clear active worker reference
        self.active_worker = None
    
    def on_worker_error(self, generation: int, error_message: str):
        """Handle worker error (runs in main thread)."""
        print(f"Worker error (generation {generation}): {error_message}")
        
        # Only show error if this is still the current generation
        if generation == self.current_generation:
            self.status_label.setText(
                f"❌ Generation {generation}: Error - {error_message}"
            )
    
    def closeEvent(self, event):
        """Clean up when window closes."""
        # Cancel extent watching
        if hasattr(self, 'extent_watch_handle'):
            self.extent_watch_handle.cancel()
        
        # Cancel active worker
        if self.active_worker is not None:
            self.active_worker.cancel()
        
        # Wait for thread pool to finish (with timeout)
        self.thread_pool.waitForDone(1000)
        
        super().closeEvent(event)


def main():
    app = QtWidgets.QApplication(sys.argv)
    
    window = BackgroundWorkerWindow()
    window.show()
    
    print("\n" + "="*70)
    print("BACKGROUND WORKER HEATMAP EXAMPLE")
    print("="*70)
    print("\nInstructions:")
    print("1. Pan and zoom the map rapidly")
    print("2. Watch the console output to see:")
    print("   - New workers starting with generation tokens")
    print("   - Previous workers being cancelled")
    print("   - Stale results being ignored")
    print("   - Latest results updating the map")
    print("\nThe GUI remains responsive because:")
    print("- Heavy computation runs in background threads (QThreadPool)")
    print("- Cancelled workers exit early (check cancel flag)")
    print("- Stale results are ignored (generation token mismatch)")
    print("="*70 + "\n")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
