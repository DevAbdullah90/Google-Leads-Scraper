"""
Empty cell detection using API-based methods.
NO FILE DOWNLOADS — uses only internet APIs (Overpass / Google Maps browser).

Methods (in AUTO priority order):
  1. OSM Buildings Check  — fast Overpass count query, checks for building density
  2. OSM Land Use Check   — Overpass tags, detects deserts / water / forests
  3. Google Maps Quick    — browser-based, most accurate but slowest

These skip unpopulated grid cells like deserts, oceans, forests, and mountains
before scraping begins — saving hours on country-wide searches.

Log coverage:
  - Per-cell result (method, is_populated, confidence)
  - Batch progress (populated / empty so far)
  - Final FilterStats (skip %, time saved estimate)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import httpx

from scraper.grid import BoundingBox, Grid, GridCell, grid_search_url
from scraper.utils import format_duration

logger = logging.getLogger(__name__)

OVERPASS_URL     = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 15.0

# Land use values → skip (desert, water, forest, etc.)
SKIP_LANDUSE: set[str] = {
    # Natural empty
    "desert", "sand", "beach", "dune",
    "water", "sea", "ocean", "lake", "pond", "reservoir", "basin",
    "forest", "wood", "scrub", "heath", "grassland", "meadow", "fell",
    "mountain", "rock", "cliff", "scree", "glacier", "ice",
    "wetland", "marsh", "swamp", "bog", "mud",
    # Non-habitable
    "military", "danger_area", "quarry", "mine", "landfill",
    # Rural / low density
    "farmland", "farmyard", "farm", "orchard", "vineyard",
}

# Land use values → populated area
POPULATED_LANDUSE: set[str] = {
    "residential", "commercial", "retail", "industrial",
    "mixed_use", "construction", "institutional",
    "civic", "education", "healthcare",
    "tourism", "hotel", "resort",
    "port", "harbour", "airport",
    "urban", "village",
}


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

class FilterMethod(Enum):
    AUTO         = "auto"
    OSM_BUILDINGS = "osm_buildings"
    OSM_LANDUSE  = "osm_landuse"
    GOOGLE_QUICK = "google_quick"
    OSM_COMBINED = "osm_combined"


@dataclass
class CellCheckResult:
    """Result of a single cell population check."""
    cell_id: str
    is_populated: bool
    confidence: float        # 0.0 – 1.0
    method: str
    details: dict = field(default_factory=dict)
    check_time_ms: float = 0.0

    def __str__(self) -> str:
        status = "POPULATED" if self.is_populated else "EMPTY"
        return f"[{status}] {self.cell_id} ({self.method}, conf={self.confidence:.0%})"


@dataclass
class FilterStats:
    """Aggregate stats from a filter_empty_cells run."""
    total_cells: int
    populated_cells: int
    empty_cells: int
    check_time_seconds: float

    @property
    def skip_percentage(self) -> float:
        if self.total_cells == 0:
            return 0.0
        return self.empty_cells / self.total_cells * 100

    @property
    def time_saved_estimate_seconds(self) -> float:
        """Rough estimate: ~30 seconds saved per skipped cell."""
        return self.empty_cells * 30.0

    def to_dict(self) -> dict:
        return {
            "total_cells": self.total_cells,
            "populated_cells": self.populated_cells,
            "empty_cells": self.empty_cells,
            "check_time_seconds": self.check_time_seconds,
            "skip_percentage": round(self.skip_percentage, 1),
            "time_saved_estimate_seconds": self.time_saved_estimate_seconds,
        }

    def __str__(self) -> str:
        return (
            f"Filter complete | {self.populated_cells}/{self.total_cells} populated | "
            f"{self.empty_cells} empty ({self.skip_percentage:.1f}% skipped) | "
            f"~{format_duration(self.time_saved_estimate_seconds)} saved | "
            f"checked in {format_duration(self.check_time_seconds)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Method 1: OSM Buildings Check (fastest)
# ─────────────────────────────────────────────────────────────────────────────

async def check_osm_buildings(
    bounds: BoundingBox,
    min_buildings: int = 5,
) -> CellCheckResult | None:
    """
    Count buildings in the area using the Overpass API.

    Sends a lightweight count query — does NOT download building geometry.
    Returns None if the API is unreachable or returns an error.
    """
    t0 = time.monotonic()
    query = (
        f"[out:json][timeout:10];"
        f"("
        f'way["building"]({bounds.south},{bounds.west},{bounds.north},{bounds.east});'
        f'relation["building"]({bounds.south},{bounds.west},{bounds.north},{bounds.east});'
        f");"
        f"out count;"
    )

    try:
        async with httpx.AsyncClient(timeout=OVERPASS_TIMEOUT) as client:
            resp = await client.post(OVERPASS_URL, data={"data": query})
            resp.raise_for_status()
            data = resp.json()

        # Overpass count response: elements[0].tags.total
        count = 0
        for el in data.get("elements", []):
            if el.get("type") == "count":
                count = int(el.get("tags", {}).get("total", 0))
                break

        is_populated = count >= min_buildings
        if count >= 100:
            confidence = 0.95
        elif count >= 50:
            confidence = 0.90
        elif count >= 20:
            confidence = 0.85
        elif count >= min_buildings:
            confidence = 0.75
        else:
            confidence = 0.65

        elapsed_ms = (time.monotonic() - t0) * 1000
        return CellCheckResult(
            cell_id="",
            is_populated=is_populated,
            confidence=confidence,
            method="osm_buildings",
            details={"building_count": count, "min_required": min_buildings},
            check_time_ms=round(elapsed_ms, 1),
        )

    except httpx.TimeoutException:
        logger.debug("[empty_cell] OSM buildings check timed out")
    except httpx.HTTPStatusError as e:
        logger.debug("[empty_cell] OSM buildings HTTP error: %s", e)
    except Exception as e:
        logger.debug("[empty_cell] OSM buildings unexpected error: %s", e)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Method 2: OSM Land Use Check
# ─────────────────────────────────────────────────────────────────────────────

async def check_osm_landuse(
    bounds: BoundingBox,
) -> CellCheckResult | None:
    """
    Check land use tags in the area using the Overpass API.

    Identifies whether the area is residential/commercial vs desert/water/forest.
    Returns None if the API is unreachable.
    """
    t0 = time.monotonic()
    bbox = f"{bounds.south},{bounds.west},{bounds.north},{bounds.east}"
    query = (
        f"[out:json][timeout:10];"
        f"("
        f'way["landuse"]({bbox});'
        f'relation["landuse"]({bbox});'
        f'way["natural"]({bbox});'
        f'relation["natural"]({bbox});'
        f");"
        f"out tags;"
    )

    try:
        async with httpx.AsyncClient(timeout=OVERPASS_TIMEOUT) as client:
            resp = await client.post(OVERPASS_URL, data={"data": query})
            resp.raise_for_status()
            data = resp.json()

        found_tags: set[str] = set()
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            for key in ("landuse", "natural", "water"):
                if key in tags:
                    found_tags.add(tags[key].lower())

        has_populated = bool(found_tags & POPULATED_LANDUSE)
        has_empty     = bool(found_tags & SKIP_LANDUSE)
        elapsed_ms    = (time.monotonic() - t0) * 1000

        if has_populated:
            return CellCheckResult(
                cell_id="", is_populated=True, confidence=0.80,
                method="osm_landuse",
                details={"populated_tags": list(found_tags & POPULATED_LANDUSE)},
                check_time_ms=round(elapsed_ms, 1),
            )
        if has_empty and not has_populated:
            return CellCheckResult(
                cell_id="", is_populated=False, confidence=0.75,
                method="osm_landuse",
                details={"empty_tags": list(found_tags & SKIP_LANDUSE)},
                check_time_ms=round(elapsed_ms, 1),
            )
        # No recognized tags — assume populated to be safe
        return CellCheckResult(
            cell_id="", is_populated=True, confidence=0.50,
            method="osm_landuse",
            details={"unknown_tags": list(found_tags)},
            check_time_ms=round(elapsed_ms, 1),
        )

    except httpx.TimeoutException:
        logger.debug("[empty_cell] OSM landuse check timed out")
    except httpx.HTTPStatusError as e:
        logger.debug("[empty_cell] OSM landuse HTTP error: %s", e)
    except Exception as e:
        logger.debug("[empty_cell] OSM landuse unexpected error: %s", e)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Method 3: Google Maps Quick Check (browser-based)
# ─────────────────────────────────────────────────────────────────────────────

async def check_google_maps_quick(
    page,
    cell: GridCell,
    query: str,
    timeout_ms: int = 8_000,
) -> CellCheckResult:
    """
    Navigate to the grid cell URL and count result cards.

    Most accurate but requires a browser page and is slower.
    Never returns None — falls back to is_populated=True on any error.
    """
    t0  = time.monotonic()
    url = grid_search_url(query, cell)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        await page.wait_for_timeout(1500)  # let results render

        # Count business result links
        results = await page.query_selector_all('a[href*="/maps/place/"]')
        count = len(results)

        elapsed_ms = (time.monotonic() - t0) * 1000

        if count >= 1:
            return CellCheckResult(
                cell_id=cell.cell_id, is_populated=True, confidence=0.95,
                method="google_maps_quick",
                details={"result_count": count},
                check_time_ms=round(elapsed_ms, 1),
            )

        # Check for explicit "no results" text
        no_results = await page.query_selector('text="No results found"')
        confidence = 0.90 if no_results else 0.70
        return CellCheckResult(
            cell_id=cell.cell_id, is_populated=False, confidence=confidence,
            method="google_maps_quick",
            details={"result_count": 0},
            check_time_ms=round(elapsed_ms, 1),
        )

    except Exception as e:
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.debug("[empty_cell] Google quick check failed for %s: %s", cell.cell_id, e)
        return CellCheckResult(
            cell_id=cell.cell_id, is_populated=True, confidence=0.30,
            method="google_maps_quick",
            details={"error": str(e)[:80]},
            check_time_ms=round(elapsed_ms, 1),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Combined dispatcher
# ─────────────────────────────────────────────────────────────────────────────

async def is_cell_populated(
    cell: GridCell,
    method: FilterMethod = FilterMethod.AUTO,
    query: Optional[str] = None,
    page=None,
    min_buildings: int = 5,
) -> CellCheckResult:
    """
    Check if a grid cell is populated using the specified method.

    AUTO mode tries OSM methods first (fast, free) and falls back to
    Google Maps browser check only when needed.
    """
    bounds = cell.to_bounds()
    result: CellCheckResult | None = None

    if method == FilterMethod.OSM_BUILDINGS:
        result = await check_osm_buildings(bounds, min_buildings)

    elif method == FilterMethod.OSM_LANDUSE:
        result = await check_osm_landuse(bounds)

    elif method == FilterMethod.GOOGLE_QUICK:
        if page is None or query is None:
            raise ValueError("GOOGLE_QUICK method requires both `page` and `query`.")
        result = await check_google_maps_quick(page, cell, query)

    elif method == FilterMethod.OSM_COMBINED:
        r1 = await check_osm_buildings(bounds, min_buildings)
        r2 = await check_osm_landuse(bounds)
        if r1 and r2:
            # populated if either says yes; average confidence
            result = CellCheckResult(
                cell_id=cell.cell_id,
                is_populated=r1.is_populated or r2.is_populated,
                confidence=(r1.confidence + r2.confidence) / 2,
                method="osm_combined",
                details={"buildings": r1.details, "landuse": r2.details},
            )
        else:
            result = r1 or r2

    elif method == FilterMethod.AUTO:
        # 1. Try buildings (fastest)
        result = await check_osm_buildings(bounds, min_buildings)
        if result and result.confidence >= 0.70:
            pass  # good enough
        else:
            # 2. Try landuse
            r2 = await check_osm_landuse(bounds)
            if r2 and r2.confidence >= 0.70:
                result = r2
            elif page and query:
                # 3. Browser fallback
                result = await check_google_maps_quick(page, cell, query)

    if result is None:
        # All methods failed — safe default: assume populated
        result = CellCheckResult(
            cell_id=cell.cell_id,
            is_populated=True,
            confidence=0.0,
            method="fallback",
            details={"reason": "All detection methods failed"},
        )

    result.cell_id = cell.cell_id
    logger.debug("[empty_cell] %s", result)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Batch filter
# ─────────────────────────────────────────────────────────────────────────────

async def filter_empty_cells(
    grid: Grid,
    method: FilterMethod = FilterMethod.AUTO,
    query: Optional[str] = None,
    page=None,
    min_buildings: int = 5,
    batch_size: int = 10,
    progress_callback=None,
) -> tuple[Grid, FilterStats]:
    """
    Filter empty cells from a grid before scraping.

    Processes cells in parallel batches (OSM methods) or sequentially
    (GOOGLE_QUICK — shared page cannot handle concurrent navigation).

    Args:
        grid:              Grid to filter (modified in-place).
        method:            Detection method.
        query:             Search query (needed for GOOGLE_QUICK).
        page:              Playwright Page (needed for GOOGLE_QUICK).
        min_buildings:     Threshold for OSM buildings check.
        batch_size:        Parallel cells per batch (ignored for GOOGLE_QUICK).
        progress_callback: Optional callback(processed, total, populated, empty).

    Returns:
        (grid, FilterStats) — grid is modified in-place with empty cells marked.
    """
    t0    = time.monotonic()
    total = len(grid.cells)
    populated_n = 0
    empty_n     = 0
    use_sequential = (method == FilterMethod.GOOGLE_QUICK)

    logger.info(
        "[filter] Checking %d cells for empty areas (method=%s)…",
        total, method.value,
    )

    if use_sequential:
        # GOOGLE_QUICK: one cell at a time (shared browser page)
        for i, cell in enumerate(grid.cells):
            result = await is_cell_populated(cell, method, query, page, min_buildings)
            if result.is_populated:
                populated_n += 1
            else:
                empty_n += 1
                grid.mark_cell_empty(cell.cell_id)

            if progress_callback:
                try:
                    progress_callback(i + 1, total, populated_n, empty_n)
                except Exception:
                    pass

            if (i + 1) % 10 == 0 or i + 1 == total:
                logger.info(
                    "[filter] %d/%d | populated=%d | empty=%d",
                    i + 1, total, populated_n, empty_n,
                )
    else:
        # OSM methods: parallel batches
        for batch_start in range(0, total, batch_size):
            batch = grid.cells[batch_start: batch_start + batch_size]
            tasks = [
                is_cell_populated(c, method, query, page, min_buildings)
                for c in batch
            ]
            results = await asyncio.gather(*tasks)

            for cell, result in zip(batch, results):
                if result.is_populated:
                    populated_n += 1
                else:
                    empty_n += 1
                    grid.mark_cell_empty(cell.cell_id)

            processed = min(batch_start + batch_size, total)
            if progress_callback:
                try:
                    progress_callback(processed, total, populated_n, empty_n)
                except Exception:
                    pass

            logger.info(
                "[filter] %d/%d | populated=%d | empty=%d",
                processed, total, populated_n, empty_n,
            )

            # Small delay between batches to be polite to Overpass
            if batch_start + batch_size < total:
                await asyncio.sleep(0.5)

    stats = FilterStats(
        total_cells=total,
        populated_cells=populated_n,
        empty_cells=empty_n,
        check_time_seconds=round(time.monotonic() - t0, 2),
    )
    logger.info("[filter] %s", stats)
    return grid, stats


# ─────────────────────────────────────────────────────────────────────────────
# Preview (dry-run sample)
# ─────────────────────────────────────────────────────────────────────────────

async def preview_filter(
    grid: Grid,
    method: FilterMethod = FilterMethod.AUTO,
    query: Optional[str] = None,
    page=None,
    min_buildings: int = 5,
    sample_size: int = 20,
) -> dict:
    """
    Sample a subset of cells to estimate how many would be filtered.

    Useful before committing to a full filter run.

    Returns:
        Dict with sample results and extrapolated estimates.
    """
    cells = grid.cells
    n = len(cells)
    actual_sample = min(sample_size, n)

    # Sample evenly across the grid
    step = max(1, n // actual_sample)
    sample = [cells[i] for i in range(0, n, step)][:actual_sample]

    populated = 0
    empty     = 0

    logger.info("[preview] Sampling %d/%d cells (method=%s)…", len(sample), n, method.value)

    for cell in sample:
        result = await is_cell_populated(cell, method, query, page, min_buildings)
        if result.is_populated:
            populated += 1
        else:
            empty += 1
        await asyncio.sleep(0.3)  # gentle rate limiting

    empty_rate          = empty / len(sample) if sample else 0
    estimated_empty     = int(n * empty_rate)
    estimated_populated = n - estimated_empty
    saved_seconds       = estimated_empty * 30

    return {
        "method_used": method.value,
        "sample_size": len(sample),
        "sample_populated": populated,
        "sample_empty": empty,
        "estimated_empty_pct": round(empty_rate * 100, 1),
        "estimated_total_cells": n,
        "estimated_total_empty": estimated_empty,
        "estimated_total_populated": estimated_populated,
        "estimated_time_saved": f"~{format_duration(saved_seconds)}",
    }
