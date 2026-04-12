"""High-performance DTED Level-2 terrain sampling utilities.

This module is designed for interactive map use-cases where terrain data needs
to be pulled quickly for dynamic viewports/polygons and displayed as a raster
heatmap overlay.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import io
import math
from pathlib import Path
from typing import Optional, Sequence, Tuple

import numpy as np
from matplotlib.path import Path as MplPath
from matplotlib import colormaps
from PIL import Image


LatLon = Tuple[float, float]
Bounds = Tuple[LatLon, LatLon]


@dataclass(frozen=True)
class TerrainLayer:
    """Raster terrain result for rendering in a map overlay."""

    grid_m: np.ndarray
    bounds: Bounds
    mask: np.ndarray


@dataclass(frozen=True)
class _TileData:
    lat_floor: int
    lon_floor: int
    elevations_m: np.ndarray  # shape: (nlat, nlon), south->north, west->east


class DTEDStore:
    """Fast DTED Level-2 accessor optimized for interactive polygon sampling.

    Directory layout is expected to match common DTED conventions, e.g.
    ``<root>/w106/n19.dt2``.
    """

    def __init__(self, root_dir: str | Path, cache_size: int = 16):
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.cache_size = max(1, int(cache_size))
        self._tile_cache: "OrderedDict[Tuple[int, int], _TileData]" = OrderedDict()
        self._coverage_bounds: Optional[Bounds] = None
        self._available_tiles: Optional[set[tuple[int, int]]] = None

    @staticmethod
    def _tile_dir_name(lon_floor: int) -> str:
        hemi = "e" if lon_floor >= 0 else "w"
        return f"{hemi}{abs(lon_floor):03d}"

    @staticmethod
    def _tile_file_name(lat_floor: int) -> str:
        hemi = "n" if lat_floor >= 0 else "s"
        return f"{hemi}{abs(lat_floor):02d}.dt2"

    def _tile_path(self, lat_floor: int, lon_floor: int) -> Path:
        return self.root_dir / self._tile_dir_name(lon_floor) / self._tile_file_name(lat_floor)

    @staticmethod
    def _parse_uhl_counts(buf: memoryview) -> Tuple[Optional[int], Optional[int]]:
        try:
            nlon = int(bytes(buf[47:51]).decode("ascii").strip())
            nlat = int(bytes(buf[51:55]).decode("ascii").strip())
            if nlon > 0 and nlat > 0:
                return nlon, nlat
        except (ValueError, UnicodeDecodeError):
            return None, None
        return None, None

    @classmethod
    def _read_dted_dt2(cls, path: Path, lat_floor: int, lon_floor: int) -> _TileData:
        raw = path.read_bytes()
        if len(raw) < 3428:
            raise ValueError(f"DTED file too small: {path}")

        buf = memoryview(raw)
        nlon, nlat = cls._parse_uhl_counts(buf)

        if not nlon or not nlat:
            nlon = 3601
            nlat = 3601

        record_len = 8 + 2 * nlat + 4
        payload = len(raw) - 3428

        if payload < record_len:
            raise ValueError(f"Invalid DTED payload length in {path}")

        expected = 3428 + nlon * record_len
        if expected != len(raw):
            inferred_nlon = payload // record_len
            if inferred_nlon > 0 and 3428 + inferred_nlon * record_len == len(raw):
                nlon = inferred_nlon
            else:
                nlon = min(nlon, payload // record_len)

        records = np.frombuffer(buf, dtype=np.uint8, count=nlon * record_len, offset=3428)
        records = records.reshape((nlon, record_len))
        sample_bytes = records[:, 8: 8 + (2 * nlat)]
        elev = sample_bytes.view(">i2").reshape((nlon, nlat)).astype(np.int16, copy=True).T

        return _TileData(lat_floor=lat_floor, lon_floor=lon_floor, elevations_m=elev)

    def _get_tile(self, lat_floor: int, lon_floor: int) -> Optional[_TileData]:
        key = (lat_floor, lon_floor)
        cached = self._tile_cache.get(key)
        if cached is not None:
            self._tile_cache.move_to_end(key)
            return cached

        tile_path = self._tile_path(lat_floor, lon_floor)
        if not tile_path.exists():
            return None

        tile = self._read_dted_dt2(tile_path, lat_floor=lat_floor, lon_floor=lon_floor)
        self._tile_cache[key] = tile
        self._tile_cache.move_to_end(key)

        while len(self._tile_cache) > self.cache_size:
            self._tile_cache.popitem(last=False)

        return tile

    def coverage_bounds(self) -> Optional[Bounds]:
        """Best-effort DTED coverage bounds derived from directory/file names."""
        if self._coverage_bounds is not None:
            return self._coverage_bounds

        lat_floors: list[int] = []
        lon_floors: list[int] = []
        available_tiles: set[tuple[int, int]] = set()
        for lon_dir in self.root_dir.iterdir():
            if not lon_dir.is_dir():
                continue
            name = lon_dir.name.lower()
            if len(name) != 4 or name[0] not in ("e", "w") or not name[1:].isdigit():
                continue
            lon = int(name[1:])
            lon_floor = lon if name[0] == "e" else -lon
            lon_floors.append(lon_floor)
            for f in lon_dir.iterdir():
                if not f.is_file():
                    continue
                stem = f.stem.lower()
                if len(stem) != 3 or stem[0] not in ("n", "s") or not stem[1:].isdigit():
                    continue
                lat = int(stem[1:])
                lat_floor = lat if stem[0] == "n" else -lat
                lat_floors.append(lat_floor)
                available_tiles.add((lat_floor, lon_floor))

        if not lat_floors or not lon_floors:
            return None

        self._coverage_bounds = (
            (float(min(lat_floors)), float(min(lon_floors))),
            (float(max(lat_floors) + 1), float(max(lon_floors) + 1)),
        )
        self._available_tiles = available_tiles
        return self._coverage_bounds

    def has_tile(self, lat_floor: int, lon_floor: int) -> bool:
        """Return True when a DTED file exists for this tile."""
        if self._available_tiles is None:
            self.coverage_bounds()
        if self._available_tiles is not None:
            return (lat_floor, lon_floor) in self._available_tiles
        return self._tile_path(lat_floor, lon_floor).exists()

    @staticmethod
    def _bilinear_sample(tile: _TileData, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        arr = tile.elevations_m
        nlat, nlon = arr.shape

        yf = (lats - tile.lat_floor) * (nlat - 1)
        xf = (lons - tile.lon_floor) * (nlon - 1)

        y0 = np.floor(yf).astype(np.int32)
        x0 = np.floor(xf).astype(np.int32)
        y1 = np.clip(y0 + 1, 0, nlat - 1)
        x1 = np.clip(x0 + 1, 0, nlon - 1)
        y0 = np.clip(y0, 0, nlat - 1)
        x0 = np.clip(x0, 0, nlon - 1)

        wy = yf - y0
        wx = xf - x0

        v00 = arr[y0, x0].astype(np.float32)
        v10 = arr[y1, x0].astype(np.float32)
        v01 = arr[y0, x1].astype(np.float32)
        v11 = arr[y1, x1].astype(np.float32)

        top = v00 * (1.0 - wx) + v01 * wx
        bottom = v10 * (1.0 - wx) + v11 * wx
        return top * (1.0 - wy) + bottom * wy

    def sample_polygon_grid(
        self,
        polygon_latlon: Sequence[LatLon],
        width: int,
        height: int,
        nodata_value: float = np.nan,
        quantize_deg: Optional[Tuple[float, float]] = None,
    ) -> TerrainLayer:
        """Sample terrain within a polygon's bounding rectangle and mask outside.

        Args:
            polygon_latlon: Polygon vertices as ``[(lat, lon), ...]``.
            width: Raster width in pixels.
            height: Raster height in pixels.
            nodata_value: Fill value when DTED data is unavailable.
            quantize_deg: Optional (lat_step_deg, lon_step_deg) used to snap
                sampling coordinates to a stable global lattice.
        """
        if len(polygon_latlon) < 3:
            raise ValueError("polygon_latlon must contain at least 3 vertices")

        lats_poly = np.array([p[0] for p in polygon_latlon], dtype=np.float64)
        lons_poly = np.array([p[1] for p in polygon_latlon], dtype=np.float64)

        lat_min = float(lats_poly.min())
        lat_max = float(lats_poly.max())
        lon_min = float(lons_poly.min())
        lon_max = float(lons_poly.max())

        lats = np.linspace(lat_min, lat_max, int(height), dtype=np.float64)
        lons = np.linspace(lon_min, lon_max, int(width), dtype=np.float64)
        if quantize_deg is not None:
            q_lat, q_lon = quantize_deg
            if q_lat > 0:
                lats = np.round(lats / q_lat) * q_lat
            if q_lon > 0:
                lons = np.round(lons / q_lon) * q_lon

        out = np.full((height, width), nodata_value, dtype=np.float32)

        lat_floors = np.floor(lats).astype(np.int32)
        lon_floors = np.floor(lons).astype(np.int32)

        def _runs(floors: np.ndarray):
            starts = np.flatnonzero(np.r_[True, floors[1:] != floors[:-1]])
            ends = np.r_[starts[1:], floors.size]
            return [(int(floors[s]), int(s), int(e)) for s, e in zip(starts, ends)]

        lat_runs = _runs(lat_floors)
        lon_runs = _runs(lon_floors)

        for lat_floor, ys, ye in lat_runs:
            sub_lats = lats[ys:ye][:, None]
            for lon_floor, xs, xe in lon_runs:
                tile = self._get_tile(lat_floor, lon_floor)
                if tile is None:
                    continue
                sub_lons = lons[xs:xe][None, :]
                out[ys:ye, xs:xe] = self._bilinear_sample(tile, lats=sub_lats, lons=sub_lons)

        is_rect = (
            len(polygon_latlon) == 4
            and np.isclose(lats_poly.min(), lat_min)
            and np.isclose(lats_poly.max(), lat_max)
            and np.isclose(lons_poly.min(), lon_min)
            and np.isclose(lons_poly.max(), lon_max)
        )
        if is_rect:
            mask = np.ones((height, width), dtype=bool)
        else:
            lat_grid, lon_grid = np.meshgrid(lats, lons, indexing="ij")
            poly_xy = np.column_stack([lons_poly, lats_poly])
            path = MplPath(poly_xy, closed=True)
            pts = np.column_stack([lon_grid.ravel(), lat_grid.ravel()])
            mask = path.contains_points(pts).reshape((height, width))

        out[~mask] = nodata_value

        return TerrainLayer(
            grid_m=out,
            bounds=((lat_min, lon_min), (lat_max, lon_max)),
            mask=mask,
        )

    @staticmethod
    def terrain_to_heatmap_png(
        terrain: TerrainLayer,
        cmap: str = "terrain",
        alpha: float = 0.85,
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
    ) -> bytes:
        """Convert sampled terrain into RGBA PNG bytes for RasterLayer overlays."""
        arr = terrain.grid_m
        valid = np.isfinite(arr)
        if not valid.any():
            rgba = np.zeros((*arr.shape, 4), dtype=np.uint8)
        else:
            data_min = float(np.nanmin(arr))
            data_max = float(np.nanmax(arr))
            lo = data_min if vmin is None else float(vmin)
            hi = data_max if vmax is None else float(vmax)
            if hi <= lo:
                hi = lo + 1e-6
            span = max(hi - lo, 1e-6)
            norm = (arr - lo) / span
            norm = np.clip(norm, 0.0, 1.0)
            rgba_f = colormaps[cmap](norm)
            rgba = (rgba_f * 255).astype(np.uint8)
            rgba[..., 3] = np.where(valid & terrain.mask, int(alpha * 255), 0).astype(np.uint8)

        img = Image.fromarray(rgba, mode="RGBA")
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        return bio.getvalue()
