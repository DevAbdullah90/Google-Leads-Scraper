"""
Grid search: divide a geographic area into cells and search each one.

Solves Google Maps' ~60–120 result cap per search by splitting a city/area
into a grid of smaller cells and issuing a coordinate-based search for each.

Public API:
    generate_grid(bounds, cell_size_km)  → list[GridCell]
    subdivide_cell(cell, divisions)      → list[GridCell]
    cell_size_to_zoom(km)                → int
    parse_bounds(str)                    → BoundingBox
    grid_search_url(query, cell)         → str

Log coverage:
 - Grid dimensions (rows × cols, total cells)
 - Cell size in km and corresponding zoom level
 - Subdivision events (cell_id, new count)
 - URL construction per cell
"""

from __future__ import annotations

import dataclasses
import logging
import math
import urllib.parse
from dataclasses import dataclass, field
from typing import Iterator

from scraper.utils import format_duration

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BoundingBox:
    """Geographic bounding box for an area."""
    north: float  # max latitude
    south: float  # min latitude
    east: float   # max longitude
    west: float   # min longitude

    def __post_init__(self) -> None:
        if self.south >= self.north:
            raise ValueError(f"south ({self.south}) must be < north ({self.north})")
        if self.west >= self.east:
            raise ValueError(f"west ({self.west}) must be < east ({self.east})")

    @property
    def center_lat(self) -> float:
        return (self.north + self.south) / 2

    @property
    def center_lng(self) -> float:
        return (self.east + self.west) / 2

    @property
    def width_km(self) -> float:
        """Approximate width of the bounding box in km."""
        lat_rad = math.radians(self.center_lat)
        return abs(self.east - self.west) * 111.0 * math.cos(lat_rad)

    @property
    def height_km(self) -> float:
        """Approximate height of the bounding box in km."""
        return abs(self.north - self.south) * 111.0

    def to_dict(self) -> dict:
        return {"north": self.north, "south": self.south, "east": self.east, "west": self.west}

    @classmethod
    def from_dict(cls, d: dict) -> "BoundingBox":
        return cls(north=d["north"], south=d["south"], east=d["east"], west=d["west"])


@dataclass
class GridCell:
    """A single cell in the search grid."""
    lat: float       # center latitude
    lng: float       # center longitude
    radius_km: float # approximate radius in km
    cell_id: str     # unique identifier e.g. "r2_c3"
    zoom: int = 15   # Google Maps zoom level for this cell

    # Grid position (populated by make_grid / generate_grid)
    row: int = 0
    col: int = 0

    # Scraping state (updated during scrape_grid)
    is_scraped: bool = False
    is_empty: bool = False
    result_count: int = 0

    def to_bounds(self) -> "BoundingBox":
        """Compute the bounding box for this cell from center + radius."""
        lat_offset = self.radius_km / 111.0
        lng_offset = self.radius_km / (111.0 * math.cos(math.radians(self.lat)))
        return BoundingBox(
            north=self.lat + lat_offset,
            south=self.lat - lat_offset,
            east=self.lng + lng_offset,
            west=self.lng - lng_offset,
        )

    def to_google_maps_url(self, query: str = "") -> str:
        """Build the Google Maps coordinate search URL for this cell."""
        return grid_search_url(query, self)


# ─────────────────────────────────────────────────────────────────────────────
# Grid generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_grid(
    bounds: BoundingBox,
    cell_size_km: float = 2.0,
) -> list[GridCell]:
    """
    Divide a bounding box into a grid of cells.

    Args:
        bounds:       Geographic area to cover.
        cell_size_km: Side length of each square cell in km.

    Returns:
        List of GridCell objects covering the entire bounding box.

    Notes:
        Cell centers are computed so the grid starts at (south, west) and
        each cell is inset by half a step so centers don't fall on edges.
        1 degree latitude ≈ 111 km (constant).
        1 degree longitude ≈ 111 km × cos(latitude) (varies with latitude).
    """
    zoom = cell_size_to_zoom(cell_size_km)

    # Degree equivalents for the given cell size
    lat_step = cell_size_km / 111.0
    avg_lat  = bounds.center_lat
    lng_step = cell_size_km / (111.0 * math.cos(math.radians(avg_lat)))

    cells: list[GridCell] = []
    row = 0
    lat = bounds.south

    while lat < bounds.north:
        col = 0
        lng = bounds.west
        while lng < bounds.east:
            center_lat = lat + lat_step / 2
            center_lng = lng + lng_step / 2
            # Only include cells whose center is within bounds
            if center_lat <= bounds.north and center_lng <= bounds.east:
                cells.append(GridCell(
                    lat=round(center_lat, 6),
                    lng=round(center_lng, 6),
                    radius_km=cell_size_km / 2,
                    cell_id=f"r{row}_c{col}",
                    zoom=zoom,
                    row=row,
                    col=col,
                ))
            lng += lng_step
            col += 1
        lat += lat_step
        row += 1

    rows = row
    cols = max((len([c for c in cells if c.cell_id.startswith("r0_")])), 1)
    logger.info(
        "Grid generated: %d rows × %d cols = %d cells | cell=%.1fkm | zoom=%d",
        rows, cols, len(cells), cell_size_km, zoom,
    )
    logger.info(
        "  Area: %.1f km × %.1f km | bounds: N=%.4f S=%.4f E=%.4f W=%.4f",
        bounds.width_km, bounds.height_km,
        bounds.north, bounds.south, bounds.east, bounds.west,
    )
    return cells


def subdivide_cell(cell: GridCell, divisions: int = 2) -> list[GridCell]:
    """
    Split a cell into `divisions × divisions` sub-cells.

    Used by adaptive/smart grid: when a cell returns too many results
    (hitting the Google cap), split it for finer coverage.

    Args:
        cell:      The parent cell to subdivide.
        divisions: Split factor per axis (2 → 4 sub-cells, 3 → 9, etc.)

    Returns:
        List of sub-cells covering the same area as the parent cell.
    """
    sub_size_km = (cell.radius_km * 2) / divisions
    sub_zoom    = cell_size_to_zoom(sub_size_km)

    lat_rad     = math.radians(cell.lat)
    half_lat_km = cell.radius_km
    half_lng_km = cell.radius_km

    lat_step = (half_lat_km * 2 / divisions) / 111.0
    lng_step = (half_lng_km * 2 / divisions) / (111.0 * math.cos(lat_rad))

    start_lat = cell.lat - half_lat_km / 111.0
    start_lng = cell.lng - half_lng_km / (111.0 * math.cos(lat_rad))

    sub_cells: list[GridCell] = []
    for r in range(divisions):
        for c in range(divisions):
            sub_lat = start_lat + (r + 0.5) * lat_step
            sub_lng = start_lng + (c + 0.5) * lng_step
            sub_cells.append(GridCell(
                lat=round(sub_lat, 6),
                lng=round(sub_lng, 6),
                radius_km=sub_size_km / 2,
                cell_id=f"{cell.cell_id}_s{r}{c}",
                zoom=sub_zoom,
            ))

    logger.info(
        "Cell %s subdivided into %d sub-cells (%.1fkm each)",
        cell.cell_id, len(sub_cells), sub_size_km,
    )
    return sub_cells


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def cell_size_to_zoom(cell_size_km: float) -> int:
    """
    Map cell diameter to the best Google Maps zoom level.

    At each zoom level, the map shows roughly:
        z17 → ~400m radius | z16 → ~800m | z15 → ~1.5km
        z14 → ~3km | z13 → ~6km | z12 → ~12km
    """
    if cell_size_km >= 16:
        return 11
    if cell_size_km >= 8:
        return 12
    if cell_size_km >= 4:
        return 13
    if cell_size_km >= 2:
        return 14
    if cell_size_km >= 1:
        return 15
    if cell_size_km >= 0.5:
        return 16
    return 17


def grid_search_url(query: str, cell: GridCell) -> str:
    """
    Build the Google Maps coordinate-based search URL for a grid cell.

    Format: https://www.google.com/maps/search/{query}/@{lat},{lng},{zoom}z
    """
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.google.com/maps/search/{encoded}/@{cell.lat},{cell.lng},{cell.zoom}z"
    logger.debug("Grid URL [%s]: %s", cell.cell_id, url)
    return url


def parse_bounds(bounds_str: str) -> BoundingBox:
    """
    Parse a bounding box from a CLI string.

    Expected format: "north,south,east,west"
    Example: "25.358,24.793,55.565,54.890"
    """
    try:
        parts = [float(x.strip()) for x in bounds_str.split(",")]
    except ValueError:
        raise ValueError(f"Bounds must be four comma-separated floats, got: {bounds_str!r}")
    if len(parts) != 4:
        raise ValueError(
            f"Bounds must be exactly 4 values (north,south,east,west), got {len(parts)}: {bounds_str!r}"
        )
    return BoundingBox(north=parts[0], south=parts[1], east=parts[2], west=parts[3])


# ─────────────────────────────────────────────────────────────────────────────
# Grid class (stateful wrapper around a list of GridCells)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Grid:
    """
    Stateful wrapper around a geographic grid of cells.

    Tracks scraping progress per cell (is_scraped, is_empty, result_count)
    and provides helper methods for filtering, stats, and serialization.
    """
    bounds: BoundingBox
    cell_size_km: float
    cells: list[GridCell] = field(default_factory=list)
    rows: int = 0
    cols: int = 0
    total_cells: int = 0

    def get_unscraped_cells(self) -> list[GridCell]:
        """Return cells not yet scraped and not marked empty."""
        return [c for c in self.cells if not c.is_scraped and not c.is_empty]

    def get_scraped_cells(self) -> list[GridCell]:
        return [c for c in self.cells if c.is_scraped]

    def get_empty_cells(self) -> list[GridCell]:
        return [c for c in self.cells if c.is_empty]

    def mark_cell_scraped(self, cell_id: str, result_count: int = 0) -> None:
        for cell in self.cells:
            if cell.cell_id == cell_id:
                cell.is_scraped = True
                cell.result_count = result_count
                return

    def mark_cell_empty(self, cell_id: str) -> None:
        for cell in self.cells:
            if cell.cell_id == cell_id:
                cell.is_empty = True
                cell.is_scraped = True  # treat as done so it won't be retried
                return

    def get_stats(self) -> dict:
        scraped  = len(self.get_scraped_cells())
        empty    = len(self.get_empty_cells())
        total    = len(self.cells)
        return {
            "total": total,
            "scraped": scraped,
            "unscraped": total - scraped,
            "empty": empty,
            "populated": total - empty,
            "result_count_total": sum(c.result_count for c in self.cells),
            "completion_pct": round(scraped / total * 100, 1) if total else 0.0,
        }

    def to_dict(self) -> dict:
        return {
            "bounds": self.bounds.to_dict(),
            "cell_size_km": self.cell_size_km,
            "rows": self.rows,
            "cols": self.cols,
            "total_cells": self.total_cells,
            "cells": [dataclasses.asdict(c) for c in self.cells],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Grid":
        g = cls(
            bounds=BoundingBox.from_dict(d["bounds"]),
            cell_size_km=d["cell_size_km"],
            rows=d.get("rows", 0),
            cols=d.get("cols", 0),
            total_cells=d.get("total_cells", 0),
        )
        g.cells = [GridCell(**c) for c in d.get("cells", [])]
        return g

    def __iter__(self) -> Iterator[GridCell]:
        return iter(self.cells)

    def __len__(self) -> int:
        return len(self.cells)


# ─────────────────────────────────────────────────────────────────────────────
# High-level helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_grid(bounds: BoundingBox, cell_size_km: float) -> Grid:
    """
    Generate a Grid covering `bounds` with cells of `cell_size_km` side length.

    Wraps `generate_grid()` and computes row/col counts from the generated cells.
    """
    cells = generate_grid(bounds, cell_size_km=cell_size_km)
    rows = max((c.row for c in cells), default=0) + 1 if cells else 0
    cols = max((c.col for c in cells), default=0) + 1 if cells else 0
    return Grid(
        bounds=bounds,
        cell_size_km=cell_size_km,
        cells=cells,
        rows=rows,
        cols=cols,
        total_cells=len(cells),
    )


def calculate_optimal_cell_size(bounds: BoundingBox) -> float:
    """
    Suggest a cell size in km based on the area of the bounding box.

    Larger areas → larger cells to keep the grid manageable.
    """
    area = bounds.width_km * bounds.height_km
    if area < 100:
        return 0.5
    if area < 500:
        return 1.0
    if area < 2_000:
        return 2.0
    if area < 10_000:
        return 3.0
    if area < 50_000:
        return 5.0
    return 10.0


def leads_per_cell(cell_size_km: float) -> int:
    """
    Estimate average leads per grid cell based on cell side length.

    Formula: min(120, cell_area_km2 × 8)
    Google Maps hard-caps results at ~120 per search regardless of area.

    Examples:
      1 km  →  1 km²  × 8 =   8 leads
      2 km  →  4 km²  × 8 =  32 leads
      3 km  →  9 km²  × 8 =  72 leads
      4 km  → 16 km²  × 8 = 120 leads  (cap reached)
      5 km  → 25 km²  × 8 = 120 leads  (cap)
    """
    return min(120, round(cell_size_km ** 2 * 8))


def estimate_scrape_time(
    grid: Grid,
    cell_size_km: float = 3.0,
    sec_per_lead: float = 36.0,
    cell_overhead_sec: float = 23.0,
) -> dict:
    """
    Estimate scrape time based on realistic per-lead timing.

    Realistic baseline (measured):
      50 leads → 30 min  →  36 sec/lead  (page load + extract + random delay)

    Per-cell lead count is derived from cell_size_km via leads_per_cell().

    Formula:
      avg_leads  = min(120, cell_size_km² × 8)
      sec/cell   = cell_overhead + (avg_leads × sec_per_lead)
      total_time = populated_cells × sec/cell

    Empty cells (already filtered) are excluded.
    """
    populated        = len([c for c in grid.cells if not c.is_empty])
    empty            = len(grid.cells) - populated
    avg_leads        = leads_per_cell(cell_size_km)
    sec_per_cell     = cell_overhead_sec + (avg_leads * sec_per_lead)
    total_sec        = populated * sec_per_cell
    total_leads      = populated * avg_leads

    return {
        "total_cells":        len(grid.cells),
        "populated_cells":    populated,
        "empty_cells":        empty,
        "cell_size_km":       cell_size_km,
        "avg_leads_per_cell": avg_leads,
        "estimated_leads":    total_leads,
        "sec_per_lead":       sec_per_lead,
        "sec_per_cell":       round(sec_per_cell),
        "estimated_seconds":  round(total_sec),
        "estimated_minutes":  round(total_sec / 60, 1),
        "estimated_hours":    round(total_sec / 3600, 2),
        "formatted":          format_duration(total_sec),
    }
