#!/usr/bin/env python3
"""Background Worker with Responsive GUI Example

This example demonstrates responsive GUI behavior during long-running computations:
- Uses `watch_view_extent` to observe map extent changes
- Offloads heavy computation to background worker (QRunnable/QThreadPool or multiprocessing)
- Implements cancel/interrupt mechanism (generation token + cancel flag)
- Updates map layer only when the latest computation finishes
- GUI remains responsive during long-running polygon/heatmap computations

Two Cancellation Approaches (selectable via checkbox):

Option 1: Threading with Generation Token (QRunnable/QThreadPool)
- Worker runs in thread pool
- Cancel flag checked between operations
- Atomic C++ operations complete but results discarded via generation token
- Safe, simple, handles 90% of use cases

Option 2: Multiprocessing with Process Termination
- Worker runs in separate process
- Can forcefully terminate even during atomic C++ operations
- More aggressive interruption (process.terminate())
- Note: May cause resource leaks; use with caution

Key Pattern:
1. Each extent change triggers a new computation with a unique generation token
2. Previous computation is cancelled (won't update UI when complete)
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
from multiprocessing import Process, Queue

import numpy as np
from PIL import Image
from matplotlib import colormaps
from matplotlib import colors as mcolors
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject, QTimer

from pyopenlayersqt import OLMapWidget, RasterStyle


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
            # NOTE: For atomic operations (large numpy/scipy calls that run entirely
            # in C++ like matrix multiplication, FFT, linear algebra), cancellation
            # won't interrupt mid-execution. The operation completes but results are
            # discarded via generation token check. Break into chunks when possible
            # to enable more responsive cancellation.
            chunk_size = max(1, self.grid_size // 10)
            for i in range(0, self.grid_size, chunk_size):
                if self.cancelled:
                    return
                
                end_i = min(i + chunk_size, self.grid_size)
                chunk_lat = grid_lat[i:end_i, :]
                chunk_lon = grid_lon[i:end_i, :]
                
                # Compute distances from each grid point to all data points
                # This numpy operation is atomic (runs in C++) but chunking allows
                # cancel checks between chunks rather than waiting for entire grid
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


def compute_heatmap_multiprocessing(extent: dict, generation: int, result_queue: Queue, 
                                    n_points: int = 500, grid_size: int = 512):
    """Multiprocessing worker function for heatmap computation.
    
    This runs in a separate process and can be terminated forcefully.
    Unlike threading, this can interrupt even atomic C++ operations.
    
    Args:
        extent: Map extent dictionary
        generation: Generation token
        result_queue: Queue to send results back to main process
        n_points: Number of random points
        grid_size: Grid size for heatmap
    """
    try:
        # Generate random points within extent
        lon_min = float(extent["lon_min"])
        lon_max = float(extent["lon_max"])
        lat_min = float(extent["lat_min"])
        lat_max = float(extent["lat_max"])
        
        rng = np.random.default_rng(generation)
        lons = lon_min + (lon_max - lon_min) * rng.random(n_points)
        lats = lat_min + (lat_max - lat_min) * rng.random(n_points)
        values = rng.random(n_points)
        
        # Create grid for heatmap
        gx = np.linspace(lon_min, lon_max, grid_size)
        gy = np.linspace(lat_min, lat_max, grid_size)
        grid_lon, grid_lat = np.meshgrid(gx, gy)
        
        # Heavy computation with IDW
        eps = 1e-12
        z = np.zeros((grid_size, grid_size), dtype=np.float64)
        
        # Process in chunks (though termination can happen anytime in multiprocessing)
        chunk_size = max(1, grid_size // 10)
        for i in range(0, grid_size, chunk_size):
            end_i = min(i + chunk_size, grid_size)
            chunk_lat = grid_lat[i:end_i, :]
            chunk_lon = grid_lon[i:end_i, :]
            
            # Atomic numpy operation - can be terminated mid-execution in multiprocessing
            d2 = (
                (chunk_lon[..., None] - lons[None, None, :]) ** 2
                + (chunk_lat[..., None] - lats[None, None, :]) ** 2
                + eps
            )
            w = 1.0 / d2
            z[i:end_i, :] = (w * values[None, None, :]).sum(axis=2) / w.sum(axis=2)
            
            # Simulate processing time
            time.sleep(0.05)
        
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
        
        # Define bounds
        bounds = [
            (lat_min, lon_min),  # Southwest corner
            (lat_max, lon_max)   # Northeast corner
        ]
        
        # Send result back via queue
        result_queue.put({
            'generation': generation,
            'png_bytes': png_bytes,
            'bounds': bounds,
            'status': 'success'
        })
        
    except Exception as e:
        # Send error back via queue
        result_queue.put({
            'generation': generation,
            'error': str(e),
            'status': 'error'
        })


class BackgroundWorkerWindow(QtWidgets.QMainWindow):
    """Main window demonstrating background worker pattern with cancellation."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Background Worker Heatmap Example - pyopenlayersqt")
        self.resize(1400, 900)
        
        # Thread pool for Option 1 (threading)
        self.thread_pool = QThreadPool.globalInstance()
        print(f"Using thread pool with max {self.thread_pool.maxThreadCount()} threads")
        
        # Multiprocessing for Option 2
        self.active_process: Optional[Process] = None
        self.result_queue: Optional[Queue] = None
        self.result_poll_timer = QTimer()
        self.result_poll_timer.timeout.connect(self._check_process_result)
        
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
        
        # Info panel with mode selector
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
        """Create info panel explaining the example with mode selector."""
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
        
        # Mode selector checkbox
        mode_container = QtWidgets.QWidget()
        mode_layout = QtWidgets.QHBoxLayout(mode_container)
        mode_layout.setContentsMargins(0, 8, 0, 0)
        
        mode_label = QtWidgets.QLabel("Cancellation Mode:")
        mode_label.setStyleSheet("font-weight: bold;")
        
        self.use_multiprocessing_checkbox = QtWidgets.QCheckBox(
            "Use Multiprocessing (Option 2 - forceful termination)"
        )
        self.use_multiprocessing_checkbox.setToolTip(
            "Option 1 (unchecked): Threading with generation token - safe, simple\n"
            "Option 2 (checked): Multiprocessing with terminate() - forceful, may leak resources"
        )
        
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.use_multiprocessing_checkbox)
        mode_layout.addStretch()
        
        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addWidget(mode_container)
        
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
        3. Start new worker with current generation (threading or multiprocessing)
        4. Worker will only update UI if generation still matches
        """
        # Increment generation to invalidate previous workers
        self.current_generation += 1
        generation = self.current_generation
        
        use_multiprocessing = self.use_multiprocessing_checkbox.isChecked()
        mode_str = "multiprocessing" if use_multiprocessing else "threading"
        
        print(f"\n=== Extent changed (generation {generation}, mode: {mode_str}) ===")
        print(f"Extent: lat [{extent['lat_min']:.2f}, {extent['lat_max']:.2f}], "
              f"lon [{extent['lon_min']:.2f}, {extent['lon_max']:.2f}], "
              f"zoom {extent['zoom']}")
        
        # Cancel previous worker/process if still running
        if use_multiprocessing:
            self._cancel_multiprocessing_worker(generation - 1)
        else:
            self._cancel_threading_worker(generation - 1)
        
        self.status_label.setText(
            f"🔄 Generation {generation} ({mode_str}): Starting heatmap computation..."
        )
        
        # Start new worker based on selected mode
        if use_multiprocessing:
            self._start_multiprocessing_worker(extent, generation)
        else:
            self._start_threading_worker(extent, generation)
    
    def _cancel_threading_worker(self, old_generation: int):
        """Cancel previous threading worker."""
        if self.active_worker is not None:
            print(f"Cancelling previous threading worker (generation {old_generation})")
            self.active_worker.cancel()
            self.active_worker = None
    
    def _cancel_multiprocessing_worker(self, old_generation: int):
        """Terminate previous multiprocessing worker."""
        if self.active_process is not None and self.active_process.is_alive():
            print(f"Terminating previous multiprocessing worker (generation {old_generation})")
            self.active_process.terminate()
            self.active_process.join(timeout=0.5)
            self.active_process = None
        
        # Stop polling for results
        self.result_poll_timer.stop()
    
    def _start_threading_worker(self, extent: dict, generation: int):
        """Start computation using threading (Option 1)."""
        worker = HeatmapWorker(
            extent=extent,
            generation=generation,
            n_points=500,
            grid_size=512
        )
        
        # Connect signals
        worker.signals.finished.connect(self.on_worker_finished)
        worker.signals.error.connect(self.on_worker_error)
        worker.signals.progress.connect(self.on_worker_progress)
        
        # Store reference to cancel if needed
        self.active_worker = worker
        
        # Start worker in thread pool
        self.thread_pool.start(worker)
        print(f"Started threading worker in background thread pool")
    
    def _start_multiprocessing_worker(self, extent: dict, generation: int):
        """Start computation using multiprocessing (Option 2)."""
        # Create new queue for results
        self.result_queue = Queue()
        
        # Create and start process
        self.active_process = Process(
            target=compute_heatmap_multiprocessing,
            args=(extent, generation, self.result_queue, 500, 512)
        )
        self.active_process.start()
        
        # Start polling for results (check every 100ms)
        self.result_poll_timer.start(100)
        
        print(f"Started multiprocessing worker in separate process (PID: {self.active_process.pid})")
    
    def _check_process_result(self):
        """Poll the result queue for multiprocessing worker results."""
        if self.result_queue is None:
            return
        
        # Non-blocking check for results
        if not self.result_queue.empty():
            try:
                result = self.result_queue.get_nowait()
                
                # Stop polling
                self.result_poll_timer.stop()
                
                # Process result
                generation = result['generation']
                
                if result['status'] == 'success':
                    self.on_worker_finished(generation, result['png_bytes'], result['bounds'])
                elif result['status'] == 'error':
                    self.on_worker_error(generation, result['error'])
                    
            except Exception as e:
                print(f"Error reading from queue: {e}")

    
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
        
        # Cancel/terminate active worker based on mode
        if self.active_worker is not None:
            self.active_worker.cancel()
        
        if self.active_process is not None and self.active_process.is_alive():
            print("Terminating active process on close...")
            self.active_process.terminate()
            self.active_process.join(timeout=1.0)
        
        # Stop polling timer
        self.result_poll_timer.stop()
        
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
    print("1. Choose cancellation mode using the checkbox:")
    print("   - Unchecked (Option 1): Threading with generation token")
    print("   - Checked (Option 2): Multiprocessing with forceful termination")
    print("2. Pan and zoom the map rapidly")
    print("3. Watch the console output to see:")
    print("   - New workers starting with generation tokens")
    print("   - Previous workers being cancelled/terminated")
    print("   - Stale results being ignored")
    print("   - Latest results updating the map")
    print("\nOption 1 (Threading):")
    print("- Heavy computation runs in background threads (QThreadPool)")
    print("- Cancelled workers exit early when possible")
    print("- Atomic C++ operations complete but results discarded")
    print("- Safe, simple, handles 90% of use cases")
    print("\nOption 2 (Multiprocessing):")
    print("- Heavy computation runs in separate process")
    print("- Process can be forcefully terminated (process.terminate())")
    print("- Can interrupt even atomic C++ operations")
    print("- May cause resource leaks - use with caution")
    print("="*70 + "\n")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
