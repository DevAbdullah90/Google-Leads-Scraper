"""
Public API — orchestrates the full scraping pipeline.

Log coverage:
 - Session start: full config dump (headless, proxy, delay, output dir)
 - Per-query: URL, expected max_results
 - Per-business: index/total, URL, result (scraped / failed / retry)
 - Long breaks and browser restarts (with reason)
 - Checkpoint saves (every 10 businesses)
 - Session end: full stats table
 - Any resume activity (query, already-scraped count)
"""

from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from config.settings import (
    BROWSER_RESTART_AFTER,
    DEFAULT_MAX_RESULTS,
    HEADLESS,
    LONG_BREAK_INTERVAL,
    LONG_BREAK_MAX,
    LONG_BREAK_MIN,
    MAX_RETRIES,
    OUTPUT_DIR,
    SCRAPER_VERSION,
)
from scraper.browser import BrowserSession, check_captcha, dismiss_consent
from scraper.extractor import extract_business
from scraper.grid import BoundingBox, GridCell, generate_grid, grid_search_url, subdivide_cell
from scraper.recovery import (
    append_business,
    build_output_path,
    clear_progress,
    finalize_output,
    load_businesses_from_jsonl,
    load_progress,
    new_progress,
    save_progress,
)
from scraper.scroll import collect_business_urls
from scraper.sheets_sync import fetch_sheet_existing_urls
from scraper.utils import format_duration, log_section, log_subsection, random_delay

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Simple function API
# ─────────────────────────────────────────────────────────────────────────────

async def scrape_leads(
    query: str | None = None,
    *,
    niche: str | None = None,
    location: str | None = None,
    max_results: int | None = DEFAULT_MAX_RESULTS,
    output_file: str | None = None,
    output_dir: str | Path = OUTPUT_DIR,
    headless: bool = HEADLESS,
    proxy: str | None = None,
    proxy_file: str | None = None,
    delay: tuple[float, float] = (3.0, 6.0),
    resume: bool = False,
    on_business_scraped: Callable | None = None,
    on_progress: Callable | None = None,
) -> list[dict]:
    """Scrape Google Maps for business leads (single query)."""
    query = _resolve_query(query, niche, location)
    scraper = GoogleMapsScraper(
        headless=headless, proxy=proxy, proxy_file=proxy_file,
        delay_range=delay, output_dir=Path(output_dir),
    )
    await scraper.initialize()
    try:
        return await scraper.scrape(
            query=query, max_results=max_results, output_file=output_file,
            resume=resume, on_business_scraped=on_business_scraped,
            on_progress=on_progress,
        )
    finally:
        await scraper.close()


async def scrape_leads_bulk(
    queries: list[str | dict],
    *,
    max_results_per_query: int | None = DEFAULT_MAX_RESULTS,
    output_dir: str | Path = OUTPUT_DIR,
    **kwargs,
) -> dict[str, list[dict]]:
    """Scrape multiple queries, each saved to its own file."""
    scraper = GoogleMapsScraper(
        headless=kwargs.pop("headless", HEADLESS),
        proxy=kwargs.pop("proxy", None),
        proxy_file=kwargs.pop("proxy_file", None),
        delay_range=kwargs.pop("delay", (3.0, 6.0)),
        output_dir=Path(output_dir),
    )
    await scraper.initialize()
    try:
        return await scraper.scrape_multiple(
            queries=[_resolve_query_from_item(q) for q in queries],
            max_results_per_query=max_results_per_query,
        )
    finally:
        await scraper.close()


def scrape_leads_sync(
    query: str | None = None,
    *,
    niche: str | None = None,
    location: str | None = None,
    max_results: int | None = DEFAULT_MAX_RESULTS,
    **kwargs,
) -> list[dict]:
    """Synchronous wrapper for non-async environments."""
    return asyncio.run(
        scrape_leads(query=query, niche=niche, location=location,
                     max_results=max_results, **kwargs)
    )


async def scrape_leads_grid(
    query: str | None = None,
    *,
    niche: str | None = None,
    location: str | None = None,
    bounds: BoundingBox | dict | None = None,
    cell_size_km: float = 2.0,
    max_results_per_cell: int | None = None,
    adaptive: bool = False,
    smart_filter: bool = False,
    filter_method: str = "auto",
    min_buildings: int = 5,
    output_dir: str | Path = OUTPUT_DIR,
    headless: bool = HEADLESS,
    proxy: str | None = None,
    proxy_file: str | None = None,
    delay: tuple[float, float] = (2.0, 4.0),
    on_business_scraped: Callable | None = None,
    on_progress: Callable | None = None,
) -> list[dict]:
    """
    Grid-search Google Maps to overcome the ~60-120 result cap per search.

    Divides the bounding box into a grid of cells and issues a
    coordinate-based search for each cell, deduplicating by place_id.

    Args:
        query:               Full search query OR use niche+location.
        niche:               Business type (e.g. "restaurants").
        location:            City/area name — used to auto-resolve bounds.
        bounds:              BoundingBox or {"north","south","east","west"} dict.
                             If None, resolved from location via cities.py / Nominatim.
        cell_size_km:        Side length of each grid cell in km (default 2.0).
        max_results_per_cell: Cap results per cell (None = all available).
        adaptive:            If True, subdivide cells that hit the result cap.
        output_dir:          Directory for JSON output files.
        headless:            Run browser headlessly.
        proxy/proxy_file:    Proxy config.
        delay:               (min_s, max_s) delay between businesses.
        on_business_scraped: Callback(dict) after each business.
        on_progress:         Callback(current, total, msg) for progress.

    Returns:
        Deduplicated list of all scraped businesses across all cells.
    """
    query = _resolve_query(query, niche, location)

    # Resolve bounds
    if bounds is None:
        # Try to extract city name from query for auto-resolution
        location_part = _extract_location_from_query(query)
        from scraper.geocoder import resolve_bounds
        resolved = await resolve_bounds(location_part) if location_part else None
        if resolved is None:
            raise ValueError(
                f"Could not auto-resolve bounds for {query!r}. "
                "Provide bounds explicitly: bounds=BoundingBox(...) or --bounds CLI flag."
            )
        bounds_obj = resolved
    elif isinstance(bounds, dict):
        bounds_obj = BoundingBox(**bounds)
    else:
        bounds_obj = bounds

    scraper = GoogleMapsScraper(
        headless=headless, proxy=proxy, proxy_file=proxy_file,
        delay_range=delay, output_dir=Path(output_dir),
    )
    await scraper.initialize()
    try:
        return await scraper.scrape_grid(
            query=query,
            bounds=bounds_obj,
            cell_size_km=cell_size_km,
            max_results_per_cell=max_results_per_cell,
            adaptive=adaptive,
            smart_filter=smart_filter,
            filter_method=filter_method,
            min_buildings=min_buildings,
            on_business_scraped=on_business_scraped,
            on_progress=on_progress,
        )
    finally:
        await scraper.close()


# ─────────────────────────────────────────────────────────────────────────────
# Class-based API
# ─────────────────────────────────────────────────────────────────────────────

class GoogleMapsScraper:
    """
    Full-featured scraper with explicit lifecycle management.

    Usage:
        async with GoogleMapsScraper(headless=True) as scraper:
            results = await scraper.scrape(query="restaurants in Dubai")
    """

    def __init__(
        self,
        *,
        headless: bool = HEADLESS,
        proxy: str | None = None,
        proxy_file: str | None = None,
        delay_range: tuple[float, float] = (3.0, 6.0),
        max_retries: int = MAX_RETRIES,
        output_dir: Path = OUTPUT_DIR,
    ) -> None:
        self.headless   = headless
        self.proxy      = proxy
        self.proxy_file = proxy_file
        self.delay_range = delay_range
        self.max_retries = max_retries
        self.output_dir  = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._session: BrowserSession | None = None
        self._start_time: float | None = None
        self._stats: dict[str, Any] = {
            "total_scraped": 0,
            "total_failed": 0,
            "total_retried": 0,
            "browser_restarts": 0,
            "long_breaks": 0,
        }

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Launch the browser. Must be called before scraping."""
        self._start_time = time.monotonic()

        log_section(logger, f"Google Maps Scraper v{SCRAPER_VERSION} — Session Start")
        logger.info("Config:")
        logger.info("  headless    = %s", self.headless)
        logger.info("  proxy       = %s", self.proxy or self.proxy_file or "none")
        logger.info("  delay_range = %.1f – %.1fs", *self.delay_range)
        logger.info("  max_retries = %d", self.max_retries)
        logger.info("  output_dir  = %s", self.output_dir)

        self._session = BrowserSession(
            headless=self.headless,
            proxy=self.proxy,
            proxy_file=self.proxy_file,
        )
        await self._session.__aenter__()
        logger.info("Session initialised ✓")

    async def close(self) -> None:
        """Shut down the browser and log session summary."""
        if self._session:
            await self._session.__aexit__(None, None, None)
            self._session = None

        elapsed = time.monotonic() - self._start_time if self._start_time is not None else 0

        log_section(logger, "Session Complete — Summary")
        logger.info("  Businesses scraped  : %d", self._stats["total_scraped"])
        logger.info("  Businesses failed   : %d", self._stats["total_failed"])
        logger.info("  Retries issued      : %d", self._stats["total_retried"])
        logger.info("  Browser restarts    : %d", self._stats["browser_restarts"])
        logger.info("  Long breaks taken   : %d", self._stats["long_breaks"])
        logger.info("  Total duration      : %s", format_duration(elapsed))
        if self._stats["total_scraped"] > 0 and elapsed > 0:
            rate = self._stats["total_scraped"] / (elapsed / 3600)
            logger.info("  Throughput          : ~%.0f businesses/hour", rate)

    async def __aenter__(self) -> "GoogleMapsScraper":
        await self.initialize()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    # ── Public scraping methods ────────────────────────────────────────────────

    async def scrape(
        self,
        query: str | None = None,
        *,
        niche: str | None = None,
        location: str | None = None,
        max_results: int | None = DEFAULT_MAX_RESULTS,
        output_file: str | None = None,
        resume: bool = False,
        on_business_scraped: Callable | None = None,
        on_progress: Callable | None = None,
    ) -> list[dict]:
        """Scrape a single query, save incrementally, return list of dicts."""
        query = _resolve_query(query, niche, location)

        log_section(logger, f"QUERY: {query!r}", char="─")
        logger.info("  Max      : %s", max_results or "unlimited")
        logger.info("  Resume   : %s", resume)

        skipped_urls: set[str] = set()
        if resume:
            logger.info("Resume mode — checking progress.json…")
            progress = await load_progress()
            if progress and progress.get("current_query") == query:
                # ── Restore the EXACT output path from the previous session ──
                saved_path = progress.get("output_file")
                if saved_path:
                    out_path = Path(saved_path)
                    logger.info("  Restored output path from progress.json: %s", out_path)
                else:
                    # Old progress.json without output_file field — fall back to new path
                    out_path = Path(output_file) if output_file else build_output_path(query, self.output_dir)
                    logger.warning(
                        "  progress.json has no output_file field — generating new path: %s",
                        out_path,
                    )

                already = progress.get("businesses_scraped", 0)
                skipped_urls = await _load_existing_urls(out_path)
                logger.info(
                    "  Resuming | checkpoint shows %d scraped | .jsonl has %d saved URLs → skipping all",
                    already, len(skipped_urls),
                )
            else:
                if progress:
                    logger.warning(
                        "progress.json is for a different query (%r) — starting fresh.",
                        progress.get("current_query"),
                    )
                out_path = Path(output_file) if output_file else build_output_path(query, self.output_dir)
                progress = new_progress([query], output_file=out_path)
        else:
            out_path = Path(output_file) if output_file else build_output_path(query, self.output_dir)
            progress = new_progress([query], output_file=out_path)

        logger.info("  Output   : %s", out_path)
        await save_progress(progress)

        results = await self._run_query(
            query=query, max_results=max_results, out_path=out_path,
            progress=progress, skipped_urls=skipped_urls,
            on_business_scraped=on_business_scraped, on_progress=on_progress,
        )
        await clear_progress()
        return results

    async def scrape_multiple(
        self,
        queries: list[str],
        *,
        max_results_per_query: int | None = DEFAULT_MAX_RESULTS,
        on_business_scraped: Callable | None = None,
        on_progress: Callable | None = None,
    ) -> dict[str, list[dict]]:
        """Scrape a list of queries sequentially, each to its own output file."""
        log_section(logger, f"BULK SCRAPE — {len(queries)} queries")
        for i, q in enumerate(queries, 1):
            logger.info("  %2d. %s", i, q)

        all_results: dict[str, list[dict]] = {}
        progress = new_progress(queries)
        await save_progress(progress)

        for i, query in enumerate(queries, start=1):
            log_section(logger, f"Query {i}/{len(queries)}: {query!r}", char="·")
            out_path = build_output_path(query, self.output_dir)
            progress["current_query"] = query
            progress["queries_remaining"] = queries[i:]
            progress["output_file"] = str(out_path)  # Save so resume can find the .jsonl
            await save_progress(progress)
            results = await self._run_query(
                query=query, max_results=max_results_per_query,
                out_path=out_path, progress=progress, skipped_urls=set(),
                on_business_scraped=on_business_scraped, on_progress=on_progress,
            )
            all_results[query] = results

            progress["queries_completed"].append(query)
            if query in progress["queries_remaining"]:
                progress["queries_remaining"].remove(query)
            await save_progress(progress)

            logger.info(
                "Query %d/%d done | %d businesses | %d remaining",
                i, len(queries), len(results), len(queries) - i,
            )

        await clear_progress()
        return all_results

    async def scrape_grid(
        self,
        query: str,
        bounds: BoundingBox,
        *,
        cell_size_km: float = 2.0,
        max_results_per_cell: int | None = None,
        adaptive: bool = False,
        smart_filter: bool = False,
        filter_method: str = "auto",
        min_buildings: int = 5,
        on_business_scraped: Callable | None = None,
        on_progress: Callable | None = None,
    ) -> list[dict]:
        """
        Grid-search Google Maps to overcome the per-search result cap.

        Generates a grid of cells covering `bounds`, issues a coordinate-based
        search URL for each cell, scrapes businesses, deduplicates by place_id,
        and saves all results to a single output file.

        Args:
            query:               Search term (e.g. "restaurants").
            bounds:              Geographic area to cover.
            cell_size_km:        Cell side length in km (smaller = more cells, more results).
            max_results_per_cell: Optional cap per cell.
            adaptive:            Subdivide dense cells that hit the result cap.
            on_business_scraped: Callback(dict) after each business.
            on_progress:         Callback(current, total, msg).

        Returns:
            Deduplicated list of all scraped business dicts.
        """
        assert self._session is not None, "Call initialize() first."

        cells = generate_grid(bounds, cell_size_km=cell_size_km)
        out_path = build_output_path(f"grid_{query}", self.output_dir)

        log_section(logger, f"GRID SEARCH — {query!r}")
        logger.info("  Cells       : %d", len(cells))
        logger.info("  Cell size   : %.1f km", cell_size_km)
        logger.info("  Adaptive    : %s", adaptive)
        logger.info("  Smart filter: %s (method=%s)", smart_filter, filter_method)
        logger.info("  Max/cell    : %s", max_results_per_cell or "unlimited")
        logger.info("  Bounds      : N=%.4f S=%.4f E=%.4f W=%.4f",
                    bounds.north, bounds.south, bounds.east, bounds.west)
        logger.info("  Output      : %s", out_path)

        # ── Smart filter: skip empty cells before scraping ────────────────
        if smart_filter:
            from scraper.empty_cell_detector import FilterMethod, filter_empty_cells
            from scraper.grid import make_grid

            try:
                fm = FilterMethod(filter_method)
            except ValueError:
                logger.warning(
                    "[smart_filter] Unknown filter_method %r — falling back to AUTO",
                    filter_method,
                )
                fm = FilterMethod.AUTO

            logger.info("[smart_filter] Filtering empty cells (method=%s, min_buildings=%d)…",
                        fm.value, min_buildings)

            grid_obj = make_grid(bounds, cell_size_km)
            # Pass page only for google_quick (shared page, sequential)
            filter_page = self._session.page if fm == FilterMethod.GOOGLE_QUICK else None
            grid_obj, filter_stats = await filter_empty_cells(
                grid_obj, method=fm, query=query,
                page=filter_page, min_buildings=min_buildings,
            )
            # Replace flat cell list with only populated cells
            cells = grid_obj.get_unscraped_cells()

            logger.info(
                "[smart_filter] Done | total=%d | populated=%d | empty=%d | "
                "skip=%.1f%% | ~%.0f min saved",
                filter_stats.total_cells, filter_stats.populated_cells,
                filter_stats.empty_cells, filter_stats.skip_percentage,
                filter_stats.time_saved_estimate_seconds / 60,
            )

        # ── Load resume state ─────────────────────────────────────────────────
        progress = await load_progress()
        seen_place_ids: set[str] = set()
        seen_urls:      set[str] = set()
        completed_cell_ids: set[str] = set()

        if progress and progress.get("mode") == "grid_search" and progress.get("query") == query:
            completed_cell_ids = set(progress.get("cells_completed", []))
            seen_place_ids     = set(progress.get("seen_place_ids", []))
            seen_urls          = set(progress.get("seen_urls", []))

            # Bootstrap seen_urls / seen_place_ids from JSONL if progress.json predates this
            # feature or was lost (JSONL is the authoritative record of what was saved).
            if (not seen_urls or not seen_place_ids) and out_path:
                jsonl_businesses = await load_businesses_from_jsonl(out_path)
                if not seen_urls:
                    seen_urls = {
                        _normalize_url(b.get("google_maps_url", ""))
                        for b in jsonl_businesses if b.get("google_maps_url")
                    }
                if not seen_place_ids:
                    seen_place_ids = {b["place_id"] for b in jsonl_businesses if b.get("place_id")}
                if seen_urls or seen_place_ids:
                    logger.info(
                        "Bootstrapped from JSONL: %d URLs, %d place_ids loaded",
                        len(seen_urls), len(seen_place_ids),
                    )

            logger.info(
                "Resuming grid session | %d/%d cells done | %d URLs seen | %d place_ids seen",
                len(completed_cell_ids), len(cells), len(seen_urls), len(seen_place_ids),
            )
        else:
            progress = {
                "session_id": str(uuid.uuid4()),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "mode": "grid_search",
                "query": query,
                "grid_config": {
                    "total_cells": len(cells),
                    "cell_size_km": cell_size_km,
                    "adaptive": adaptive,
                    "bounds": bounds.to_dict(),
                },
                "cells_completed": [],
                "cells_remaining": [c.cell_id for c in cells],
                "current_cell": None,
                "businesses_scraped": 0,
                "businesses_failed": 0,
                "unique_place_ids": 0,
                "duplicates_skipped": 0,
                "seen_place_ids": [],
                "seen_urls": [],
                "output_file": str(out_path),
            }
        await save_progress(progress)

        all_results: list[dict] = []

        # ── Cell processing loop ──────────────────────────────────────────────
        pending_cells = [c for c in cells if c.cell_id not in completed_cell_ids]
        total_cells   = len(cells)

        for cell_idx, cell in enumerate(pending_cells, start=1):
            log_section(
                logger,
                f"CELL {cell.cell_id} [{cell_idx}/{len(pending_cells)}] "
                f"({cell_idx + len(completed_cell_ids)}/{total_cells} total)",
                char="·",
            )
            logger.info("  Center: (%.6f, %.6f) | zoom=%d", cell.lat, cell.lng, cell.zoom)

            progress["current_cell"] = cell.cell_id
            progress["cells_remaining"] = [c.cell_id for c in pending_cells[cell_idx:]]
            await save_progress(progress)

            # Build coordinate-based URL and scrape this cell
            cell_url = grid_search_url(query, cell)
            cell_results = await self._run_grid_cell(
                query=query,
                cell=cell,
                cell_url=cell_url,
                out_path=out_path,
                progress=progress,
                seen_place_ids=seen_place_ids,
                seen_urls=seen_urls,
                max_results=max_results_per_cell,
                on_business_scraped=on_business_scraped,
                on_progress=on_progress,
                cell_idx=cell_idx,
                total_cells=len(pending_cells),
            )

            # Adaptive subdivision: if cell hit the cap, subdivide and queue
            if adaptive and max_results_per_cell and len(cell_results) >= max_results_per_cell:
                logger.info(
                    "Cell %s hit cap (%d results) — subdividing into 4 sub-cells",
                    cell.cell_id, len(cell_results),
                )
                sub_cells = subdivide_cell(cell, divisions=2)
                for sub_cell in sub_cells:
                    if sub_cell.cell_id not in completed_cell_ids:
                        sub_url = grid_search_url(query, sub_cell)
                        sub_results = await self._run_grid_cell(
                            query=query, cell=sub_cell, cell_url=sub_url,
                            out_path=out_path, progress=progress,
                            seen_place_ids=seen_place_ids,
                            seen_urls=seen_urls,
                            max_results=max_results_per_cell,
                            on_business_scraped=on_business_scraped,
                            on_progress=on_progress,
                            cell_idx=cell_idx, total_cells=total_cells,
                        )
                        all_results.extend(sub_results)

            all_results.extend(cell_results)
            completed_cell_ids.add(cell.cell_id)
            progress["cells_completed"].append(cell.cell_id)
            progress["seen_place_ids"] = list(seen_place_ids)
            progress["seen_urls"]      = list(seen_urls)
            await save_progress(progress)

            logger.info(
                "Cell %s done | +%d new | total unique=%d | duplicates skipped=%d",
                cell.cell_id, len(cell_results),
                progress["unique_place_ids"], progress["duplicates_skipped"],
            )

            # Delay between cells
            await random_delay(*self.delay_range)

        # ── Finalize ──────────────────────────────────────────────────────────
        metadata = {
            "query": query,
            "mode": "grid_search",
            "grid_config": progress.get("grid_config", {}),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "scraper_version": SCRAPER_VERSION,
        }
        await finalize_output(out_path, metadata)
        await clear_progress()

        log_section(logger, "GRID SEARCH COMPLETE")
        logger.info("  Total unique businesses : %d", progress["unique_place_ids"])
        logger.info("  Duplicates skipped      : %d", progress["duplicates_skipped"])
        logger.info("  Cells completed         : %d / %d", len(completed_cell_ids), total_cells)
        logger.info("  Output                  : %s", out_path)

        return all_results

    async def _run_grid_cell(
        self,
        query: str,
        cell: GridCell,
        cell_url: str,
        out_path: Path,
        progress: dict,
        seen_place_ids: set[str],
        seen_urls: set[str],
        max_results: int | None,
        on_business_scraped: Callable | None,
        on_progress: Callable | None,
        cell_idx: int,
        total_cells: int,
    ) -> list[dict]:
        """Navigate to a grid cell URL, collect + scrape businesses, deduplicate."""
        assert self._session is not None
        page = self._session.page
        assert page is not None

        # Navigate to the grid cell search URL
        logger.info("  Navigating to cell URL: %s", cell_url)
        for attempt in range(1, self.max_retries + 1):
            try:
                await page.goto(cell_url, wait_until="domcontentloaded", timeout=30_000)
                break
            except Exception as e:
                logger.warning("  Nav attempt %d/%d failed: %s", attempt, self.max_retries, e)
                if attempt == self.max_retries:
                    logger.error("  All navigation attempts failed for cell %s", cell.cell_id)
                    return []
                await random_delay(2 ** attempt, 2 ** attempt * 1.5)

        from scraper.browser import dismiss_consent, check_captcha
        await dismiss_consent(page)
        if await check_captcha(page):
            logger.error("  CAPTCHA detected on cell %s — restarting browser and backing off", cell.cell_id)
            self._stats["browser_restarts"] += 1
            await self._session.restart()
            page = self._session.page
            await random_delay(300, 900)
            return []

        # Collect business URLs for this cell
        business_urls = await collect_business_urls(page, max_results=max_results)
        if not business_urls:
            logger.warning("  No URLs found for cell %s", cell.cell_id)
            return []

        logger.info("  Cell %s: %d URLs collected", cell.cell_id, len(business_urls))

        # ── Deduplicate before scraping ───────────────────────────────────────
        # Layer 1: normalized URL match  — works for every URL format (always reliable)
        # Layer 2: place_id extracted from URL — secondary guard, catches edge cases
        new_urls: list[str] = []
        for url in business_urls:
            norm = _normalize_url(url)
            if norm in seen_urls:
                progress["duplicates_skipped"] = progress.get("duplicates_skipped", 0) + 1
                continue
            place_id = _extract_place_id_from_url(url)
            if place_id and place_id in seen_place_ids:
                progress["duplicates_skipped"] = progress.get("duplicates_skipped", 0) + 1
                # Also register URL so future cells skip it without extracting place_id
                seen_urls.add(norm)
                continue
            new_urls.append(url)

        skipped = len(business_urls) - len(new_urls)
        logger.info(
            "  Cell %s: %d collected → %d new to scrape, %d duplicates skipped",
            cell.cell_id, len(business_urls), len(new_urls), skipped,
        )

        results: list[dict] = []
        for idx, url in enumerate(new_urls, start=1):
            if on_progress:
                try:
                    r = on_progress(idx, len(new_urls), f"[cell {cell.cell_id}] [{idx}/{len(new_urls)}]")
                    if hasattr(r, "__await__"):
                        await r
                except Exception:
                    pass

            # Browser restart check
            scraped_total = self._stats["total_scraped"]
            if scraped_total > 0 and scraped_total % BROWSER_RESTART_AFTER == 0:
                logger.info("Browser restart (every %d businesses)", BROWSER_RESTART_AFTER)
                self._stats["browser_restarts"] += 1
                await self._session.restart()
                page = self._session.page

            business = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    business = await asyncio.wait_for(
                        extract_business(page, url, query,
                                         on_business_scraped=on_business_scraped),
                        timeout=300.0,  # 5-min hard cap per business
                    )
                    if business:
                        break
                    if attempt < self.max_retries:
                        await random_delay(2 ** (attempt - 1), 2 ** (attempt - 1) * 1.5)
                        self._stats["total_retried"] += 1
                except asyncio.TimeoutError:
                    logger.warning("  ⏱ Business timed out (>300s) — skipping: %s", url)
                    self._stats["total_failed"] += 1
                    progress["businesses_failed"] = progress.get("businesses_failed", 0) + 1
                    break
                except Exception as e:
                    if attempt < self.max_retries:
                        await random_delay(2 ** (attempt - 1), 2 ** (attempt - 1) * 1.5)
                        self._stats["total_retried"] += 1
                    else:
                        logger.error("  Failed all retries for %s: %s", url, e)

            if business:
                place_id = business.place_id
                if place_id and place_id in seen_place_ids:
                    # Post-scrape safety net (URL dedup should have caught this earlier)
                    logger.debug("  ↩ DUPLICATE skipped (post-scrape): %r", business.business_name)
                    progress["duplicates_skipped"] = progress.get("duplicates_skipped", 0) + 1
                    seen_urls.add(_normalize_url(url))  # register so future cells skip it
                    continue
                if place_id:
                    seen_place_ids.add(place_id)

                # Register the URL so every future cell skips this business without visiting it
                seen_urls.add(_normalize_url(url))

                d = business.to_dict()
                if await append_business(out_path, d):
                    results.append(d)
                    self._stats["total_scraped"] += 1
                    progress["businesses_scraped"] = progress.get("businesses_scraped", 0) + 1
                    progress["unique_place_ids"]   = len(seen_place_ids)
                    logger.debug("  ✔ SAVED [#%d]: %r", self._stats["total_scraped"], business.business_name)
                else:
                    self._stats["total_failed"] += 1
                    progress["businesses_failed"] = progress.get("businesses_failed", 0) + 1
            else:
                self._stats["total_failed"] += 1
                progress["businesses_failed"] = progress.get("businesses_failed", 0) + 1

            await random_delay(*self.delay_range)

        return results

    async def resume(self) -> list[dict]:
        """Resume the most recently interrupted session."""
        logger.info("Resuming previous session…")
        progress = await load_progress()
        if not progress:
            logger.warning("No progress.json found — nothing to resume.")
            return []
        query = progress.get("current_query", "")
        if not query:
            logger.warning("progress.json has no current_query — cannot resume.")
            return []
        logger.info("Resuming query: %r", query)
        return await self.scrape(query=query, resume=True)

    def get_stats(self) -> dict[str, Any]:
        elapsed = time.monotonic() - self._start_time if self._start_time else 0
        return {**self._stats, "duration": format_duration(elapsed)}

    def export(self, data: list[dict], fmt: str = "json") -> str:
        import json
        if fmt == "json":
            return json.dumps(data, indent=2, ensure_ascii=False)
        raise ValueError(f"Unsupported export format: {fmt!r}")

    # ── Internal: single query runner ─────────────────────────────────────────

    async def _run_query(
        self,
        query: str,
        max_results: int | None,
        out_path: Path,
        progress: dict,
        skipped_urls: set[str],
        on_business_scraped: Callable | None,
        on_progress: Callable | None,
    ) -> list[dict]:
        assert self._session is not None, "Call initialize() first."
        page = self._session.page
        assert page is not None

        # ── Navigate to search results ──────────────────────────────────────
        search_url = _build_search_url(query)
        logger.info("Navigating to search URL: %s", search_url)

        for attempt in range(1, self.max_retries + 1):
            try:
                await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
                logger.info("Search page loaded ✓ (attempt %d)", attempt)
                break
            except Exception as e:
                logger.warning(
                    "Navigation attempt %d/%d failed: %s",
                    attempt, self.max_retries, e,
                )
                if attempt == self.max_retries:
                    logger.error(
                        "All %d navigation attempts failed — aborting query: %r",
                        self.max_retries, query,
                    )
                    return []
                backoff = 2 ** attempt
                logger.info("Backing off %.0fs before retry…", backoff)
                await random_delay(backoff, backoff * 1.5)

        await dismiss_consent(page)

        if await check_captcha(page):
            logger.error(
                "CAPTCHA on search page for query %r — restarting browser and backing off 5–15 min.",
                query,
            )
            self._stats["browser_restarts"] += 1
            await self._session.restart()
            page = self._session.page
            await random_delay(300, 900)
            return []

        # ── Collect business URLs with Google Sheet pre-scrape skipping ──────
        logger.info("Checking Google Sheet history for pre-scrape skipping…")
        sheet_skipped = fetch_sheet_existing_urls()
        combined_skipped = set(skipped_urls) | sheet_skipped

        logger.info("Collecting business URLs (max=%s)…", max_results or "unlimited")
        business_urls = await collect_business_urls(
            page, max_results=max_results, skipped_urls=combined_skipped
        )

        if not business_urls:
            logger.warning("No business URLs found for query: %r", query)
            logger.warning(
                "  Possible causes: zero results on Google, CAPTCHA, "
                "or RESULTS_FEED_SELECTORS need updating."
            )
            return []

        to_scrape = [u for u in business_urls if u not in combined_skipped]
        skipped_count = len(business_urls) - len(to_scrape)
        total = len(to_scrape)

        logger.info(
            "URLs: %d collected | %d skipped (already scraped) | %d to process",
            len(business_urls), skipped_count, total,
        )

        results: list[dict] = []

        for idx, url in enumerate(to_scrape, start=1):

            # ── Long break every N businesses ─────────────────────────────
            if idx > 1 and (idx - 1) % LONG_BREAK_INTERVAL == 0:
                logger.info(
                    "━━ Long break after %d businesses (%.0f – %.0fs) ━━",
                    idx - 1, LONG_BREAK_MIN, LONG_BREAK_MAX,
                )
                self._stats["long_breaks"] += 1
                await random_delay(LONG_BREAK_MIN, LONG_BREAK_MAX)

            # ── Browser restart every N businesses ────────────────────────
            if idx > 1 and (idx - 1) % BROWSER_RESTART_AFTER == 0:
                logger.info(
                    "━━ Browser restart (every %d businesses) ━━",
                    BROWSER_RESTART_AFTER,
                )
                self._stats["browser_restarts"] += 1
                await self._session.restart()
                page = self._session.page
                logger.info("  Re-navigating to search page after restart…")
                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
                    await dismiss_consent(page)
                except Exception as e:
                    logger.warning("  Post-restart navigation failed: %s", e)

            # ── Progress callback ─────────────────────────────────────────
            if on_progress:
                try:
                    r = on_progress(idx, total, f"[{idx}/{total}] {url}")
                    if hasattr(r, "__await__"):
                        await r
                except Exception as e:
                    logger.debug("on_progress callback error: %s", e)

            # ── Per-business header ───────────────────────────────────────
            log_subsection(
                logger,
                f"Business {idx}/{total}  [{(idx/total*100):.0f}%]",
                char="─",
            )
            logger.debug("  URL: %s", url)

            # ── Scrape with retry ─────────────────────────────────────────
            business = None
            for attempt in range(1, self.max_retries + 1):
                try:
                    business = await asyncio.wait_for(
                        extract_business(page, url, query,
                                         on_business_scraped=on_business_scraped),
                        timeout=300.0,  # 5-min hard cap per business
                    )
                    if business is not None:
                        break
                    # extract_business returned None (not an exception)
                    if attempt < self.max_retries:
                        backoff = 2 ** (attempt - 1)
                        logger.warning(
                            "  Attempt %d/%d returned None — retrying in %.0fs",
                            attempt, self.max_retries, backoff,
                        )
                        self._stats["total_retried"] += 1
                        await random_delay(backoff, backoff * 1.5)
                except asyncio.TimeoutError:
                    logger.warning("  ⏱ Business timed out (>300s) — skipping: %s", url)
                    self._stats["total_failed"] += 1
                    progress["businesses_failed"] = progress.get("businesses_failed", 0) + 1
                    break
                except Exception as e:
                    if attempt < self.max_retries:
                        backoff = 2 ** (attempt - 1)
                        logger.warning(
                            "  Attempt %d/%d raised exception: %s — retrying in %.0fs",
                            attempt, self.max_retries, e, backoff,
                        )
                        self._stats["total_retried"] += 1
                        await random_delay(backoff, backoff * 1.5)
                    else:
                        logger.error(
                            "  All %d attempts exhausted for: %s | error: %s",
                            self.max_retries, url, e,
                        )

            # ── Record result ─────────────────────────────────────────────
            if business:
                d = business.to_dict()
                if await append_business(out_path, d):
                    results.append(d)
                    self._stats["total_scraped"] += 1
                    progress["businesses_scraped"] += 1
                    progress["last_place_id"] = business.place_id
                else:
                    self._stats["total_failed"] += 1
                    progress["businesses_failed"] += 1
            else:
                self._stats["total_failed"] += 1
                progress["businesses_failed"] += 1
                logger.warning(
                    "  ✗ FAILED business %d/%d: %s", idx, total, url
                )

            # ── Checkpoint every 10 ───────────────────────────────────────
            if idx % 10 == 0:
                logger.debug("Checkpoint save at business %d/%d…", idx, total)
                await save_progress(progress)

            # ── Delay between businesses ──────────────────────────────────
            await random_delay(*self.delay_range)

        # ── Finalise output ───────────────────────────────────────────────
        logger.info("All %d businesses processed — finalising output…", total)
        metadata = {
            "query": query,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "scraper_version": SCRAPER_VERSION,
        }
        count = await finalize_output(out_path, metadata)
        logger.info(
            "Query complete | scraped=%d | failed=%d | output=%s",
            len(results), total - len(results), out_path.name,
        )
        return results


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_query(q: str | None, niche: str | None, location: str | None) -> str:
    if q:
        return q.strip()
    if niche and location:
        return f"{niche.strip()} in {location.strip()}"
    if niche:
        return niche.strip()
    if location:
        return location.strip()
    raise ValueError("Provide `query` or at least one of `niche`/`location`.")


def _resolve_query_from_item(item: str | dict) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return _resolve_query(item.get("query"), item.get("niche"), item.get("location"))
    raise TypeError(f"Query must be str or dict, got {type(item)}")


def _build_search_url(query: str) -> str:
    url = f"https://www.google.com/maps/search/{urllib.parse.quote_plus(query)}/"
    logger.debug("Search URL: %s", url)
    return url


async def _load_existing_urls(out_path: Path) -> set[str]:
    businesses = await load_businesses_from_jsonl(out_path)
    urls = {b.get("google_maps_url", "") for b in businesses if b.get("google_maps_url")}
    logger.debug("Loaded %d existing URLs from previous JSONL", len(urls))
    return urls


def _extract_place_id_from_url(url: str) -> str | None:
    """
    Extract the Google Maps place_id (ChIJ...) from a business URL.

    Google embeds the place_id in the data segment of the URL:
        /data=!...!1sChIJxxxxxxxx...
    Falls back to the `place_id` query parameter if present.
    """
    import re
    # Primary: !1s<place_id> in the data path segment
    match = re.search(r"!1s(ChIJ[^!&?]+)", url)
    if match:
        return urllib.parse.unquote(match.group(1))
    # Fallback: ?place_id=... or &place_id=...
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    if "place_id" in params:
        return params["place_id"][0]
    return None


def _normalize_url(url: str) -> str:
    """
    Normalize a Google Maps business URL to a stable key for deduplication.

    Strips query parameters, fragments, and trailing slashes so that the
    same business reached via different entry points produces the same key.

    Example:
        https://www.google.com/maps/place/Café+XYZ/@25.19,55.27,17z/data=!...
        → https://www.google.com/maps/place/Café+XYZ/@25.19,55.27,17z/data=!...
    We keep the path (which contains the place name + coords + data) and drop
    anything after '?' or '#'.
    """
    # Keep only scheme + netloc + path; drop query string and fragment
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def _extract_location_from_query(query: str) -> str | None:
    """
    Extract the location part from a search query string.

    Examples:
        "restaurants in Dubai"       → "Dubai"
        "cafes in New York"          → "New York"
        "hotels in Kuala Lumpur"     → "Kuala Lumpur"
        "plumbers"                   → None
    """
    import re
    match = re.search(r"\bin\s+(.+)$", query.strip(), re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None
