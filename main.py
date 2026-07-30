"""
Google Maps Business Leads Scraper — CLI entry point.

Usage examples:
    python main.py --query "restaurants in Dubai" --max-results 100
    python main.py --file queries.csv
    python main.py --interactive
    python main.py --resume
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from config.settings import OUTPUT_DIR, SCRAPER_VERSION
from scraper.api import GoogleMapsScraper, _extract_location_from_query
from scraper.grid import parse_bounds
from scraper.recovery import load_progress
from scraper.utils import enable_debug, logger

console = Console()


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="main.py",
        description="Google Maps Business Leads Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --query "coffee shops in Dubai" --max-results 50
  python main.py --file queries.csv --max-results 100
  python main.py --interactive
  python main.py --resume
  python main.py --query "..." --proxy-file proxies.txt --debug
        """,
    )

    mode = p.add_mutually_exclusive_group()
    mode.add_argument("-q", "--query", metavar="QUERY",
                      help='Single search query, e.g. "restaurants in Dubai"')
    mode.add_argument("-f", "--file", metavar="FILE",
                      help="CSV or TXT file containing queries (one per line)")
    mode.add_argument("-i", "--interactive", action="store_true",
                      help="Prompt for niche and location interactively")
    mode.add_argument("-r", "--resume", action="store_true",
                      help="Resume the last interrupted session")

    p.add_argument("-m", "--max-results", type=int, default=None, metavar="N",
                   help="Maximum results per query (default: unlimited)")
    p.add_argument("-o", "--output-dir", default=str(OUTPUT_DIR), metavar="DIR",
                   help=f"Output directory (default: {OUTPUT_DIR})")
    p.add_argument("-p", "--proxy-file", metavar="FILE",
                   help="Path to proxy list file")
    p.add_argument("--proxy", metavar="URL",
                   help="Single proxy URL (e.g. http://user:pass@host:port)")
    p.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True,
                   help="Run in headless mode (default: on)")
    p.add_argument("--delay", type=float, default=3.0, metavar="SEC",
                   help="Minimum delay between requests in seconds (default: 3)")
    p.add_argument("--debug", action="store_true",
                   help="Enable verbose debug logging")

    # Grid search options
    grid = p.add_argument_group("Grid search (overcomes Google's ~60-120 result cap)")
    grid.add_argument("--grid", action="store_true",
                      help="Enable grid search mode — divide the area into cells")
    grid.add_argument("--cell-size", type=float, default=2.0, metavar="KM",
                      help="Grid cell side length in km (default: 2.0). "
                           "Smaller = more cells, more results, slower.")
    grid.add_argument("--bounds", metavar="N,S,E,W",
                      help='Bounding box as "north,south,east,west" decimals, '
                           'e.g. "25.358,24.793,55.565,54.890". '
                           "If omitted, auto-resolved from the location in your query.")
    grid.add_argument("--adaptive", action="store_true",
                      help="Subdivide cells that hit the result cap (requires --max-results)")

    # Country & Smart Filter options
    smart = p.add_argument_group("Country & Smart Filter")
    smart.add_argument("--country", metavar="COUNTRY",
                       help="Country context for geocoding (e.g. 'UAE', 'UK'). "
                            "Improves accuracy when city name is ambiguous.")
    smart.add_argument("--smart-filter", action="store_true",
                       help="Filter empty cells (deserts, water, forests) before scraping. "
                            "Saves hours on country-wide searches. Use with --grid.")
    smart.add_argument("--filter-method",
                       choices=["auto", "osm_buildings", "osm_landuse", "google_quick"],
                       default="auto",
                       help="Empty cell detection method (default: auto). "
                            "auto tries OSM first, falls back to Google Maps.")
    smart.add_argument("--min-buildings", type=int, default=5, metavar="N",
                       help="Min buildings for osm_buildings check (default: 5)")
    smart.add_argument("--estimate-only", action="store_true",
                       help="Print grid size and time estimate then exit (no browser, no scraping)")
    smart.add_argument("--filter-preview", action="store_true",
                       help="Sample cells to estimate how many would be filtered (dry run, no scraping)")

    return p


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.debug:
        enable_debug()

    _print_banner()

    # ----------------------------------------------------------------
    # Resolve queries from arguments
    # ----------------------------------------------------------------
    queries: list[str] = []
    bounds = None  # may be set by --resume grid restore or --bounds flag below

    if args.resume:
        progress = await load_progress()
        if not progress:
            console.print("[red]No progress.json found — nothing to resume.[/red]")
            return 1
        # Grid sessions use "query", regular sessions use "current_query"
        current = progress.get("current_query") or progress.get("query", "")
        if not current:
            console.print("[red]progress.json has no query field — cannot resume.[/red]")
            return 1
        queries = [current] + progress.get("queries_remaining", [])

        # Detect grid session and restore bounds + cell size
        if progress.get("mode") == "grid_search":
            gc = progress.get("grid_config", {})
            b  = gc.get("bounds", {})
            if b:
                from scraper.grid import BoundingBox
                bounds    = BoundingBox(
                    north=b["north"], south=b["south"],
                    east=b["east"],  west=b["west"],
                )
                # Override args so the execution block uses grid mode
                args.grid      = True
                args.cell_size = gc.get("cell_size_km", args.cell_size)
                args.adaptive  = gc.get("adaptive", False)
                console.print(
                    f"[green]Resuming grid session:[/green] {progress.get('businesses_scraped', 0)} scraped | "
                    f"{len(progress.get('cells_completed', []))}/{gc.get('total_cells', '?')} cells done"
                )
            else:
                console.print("[red]Grid progress.json has no bounds — cannot resume.[/red]")
                return 1
        else:
            console.print(
                f"[green]Resuming:[/green] {len(queries)} query/queries remaining "
                f"({progress.get('businesses_scraped', 0)} already scraped)."
            )

    elif args.interactive:
        queries = _interactive_input()

    elif args.query:
        queries = [args.query]

    elif args.file:
        queries = _load_queries_from_file(args.file)
        if not queries:
            console.print(f"[red]No queries found in {args.file}[/red]")
            return 1

    else:
        parser.print_help()
        return 0

    # ----------------------------------------------------------------
    # Run scraper
    # ----------------------------------------------------------------
    output_dir  = Path(args.output_dir)
    delay_range = (args.delay, args.delay * 2)
    country     = getattr(args, "country", None)

    # Parse --bounds if provided (only if not already set by grid resume above)
    if bounds is None and hasattr(args, "bounds") and args.bounds:
        try:
            bounds = parse_bounds(args.bounds)
        except ValueError as e:
            console.print(f"[red]Invalid --bounds: {e}[/red]")
            return 1

    # ── Grid mode: resolve bounds early (needed for --estimate-only/--filter-preview) ──
    if getattr(args, "grid", False) and bounds is None:
        if len(queries) != 1:
            console.print("[red]Grid mode supports only a single --query.[/red]")
            return 1

        location_part = _extract_location_from_query(queries[0]) if queries else None
        if not location_part and not country:
            console.print(
                "[red]Grid mode: cannot auto-resolve bounds. "
                'Use --bounds "N,S,E,W", add " in <city>" to your query, or use --country.[/red]'
            )
            return 1

        from scraper.geocoder import resolve_bounds
        target = location_part or country
        console.print(f"[cyan]Auto-resolving bounds for:[/cyan] {target!r}")
        bounds = await resolve_bounds(target or "", country=country)
        if bounds is None:
            console.print(
                f"[red]Could not resolve bounds for {target!r}. "
                "Try a more specific name (e.g. 'Dubai, UAE') or use --bounds N,S,E,W.[/red]"
            )
            return 1

    # ── --estimate-only: print estimate and exit (no browser needed) ──────
    if getattr(args, "estimate_only", False):
        if not getattr(args, "grid", False) or bounds is None:
            console.print("[red]--estimate-only requires --grid and a resolvable location.[/red]")
            return 1
        from scraper.grid import calculate_optimal_cell_size, estimate_scrape_time, make_grid
        cell_size = args.cell_size
        grid_obj  = make_grid(bounds, cell_size)
        est       = estimate_scrape_time(grid_obj, cell_size_km=cell_size)
        console.print(f"\n[bold]Grid estimate for:[/bold] {queries[0] if queries else '?'!r}")
        console.print(f"  Cell size        : {cell_size} km  ({cell_size**2:.0f} km²)")
        console.print(f"  Total cells      : {est['total_cells']:,}")
        console.print(f"  Avg leads/cell   : ~{est['avg_leads_per_cell']}  (= min(120, {cell_size:.0f}km² × 8))")
        console.print(f"  Est. leads total : ~{est['estimated_leads']:,}")
        console.print(f"  Assumption       : {est['sec_per_lead']:.0f}s/lead  (50 leads = 30 min measured)")
        console.print(f"  Time/cell        : ~{est['sec_per_cell']}s  (23s overhead + {est['avg_leads_per_cell']} leads × {est['sec_per_lead']:.0f}s)")
        console.print(f"  Est. time        : {est['formatted']}  ({est['estimated_hours']:.1f}h / {round(est['estimated_minutes'])} min)")
        console.print(f"  Bounds           : N={bounds.north:.4f} S={bounds.south:.4f} "
                      f"E={bounds.east:.4f} W={bounds.west:.4f}")
        console.print(f"  Area             : ~{bounds.width_km:.0f} km × {bounds.height_km:.0f} km\n")
        return 0

    scraper = GoogleMapsScraper(
        headless=args.headless,
        proxy=args.proxy,
        proxy_file=args.proxy_file,
        delay_range=delay_range,
        output_dir=output_dir,
    )

    total_scraped = 0

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress_bar:

        def on_progress(current: int, total: int, message: str) -> None:
            if not hasattr(on_progress, "_task_id"):
                on_progress._task_id = progress_bar.add_task(  # type: ignore[attr-defined]
                    queries[0] if len(queries) == 1 else "Scraping…",
                    total=total,
                )
            progress_bar.update(on_progress._task_id, completed=current)  # type: ignore[attr-defined]

        await scraper.initialize()
        try:
            # ── --filter-preview: sample cells then exit ──────────────────
            if getattr(args, "filter_preview", False):
                if not getattr(args, "grid", False) or bounds is None:
                    console.print("[red]--filter-preview requires --grid and a resolvable location.[/red]")
                    await scraper.close()
                    return 1
                from scraper.empty_cell_detector import FilterMethod, preview_filter
                from scraper.grid import make_grid
                fm       = FilterMethod(getattr(args, "filter_method", "auto"))
                grid_obj = make_grid(bounds, args.cell_size)
                console.print(f"\n[bold]Filter preview[/bold] (method={fm.value}, "
                              f"sample of 20 / {len(grid_obj)} cells)…\n")
                preview = await preview_filter(grid_obj, method=fm, sample_size=20)
                console.print(f"  Method used              : {preview['method_used']}")
                console.print(f"  Sample size              : {preview['sample_size']}")
                console.print(f"  Populated in sample      : {preview['sample_populated']}")
                console.print(f"  Empty in sample          : {preview['sample_empty']}")
                console.print(f"  Estimated empty %        : {preview['estimated_empty_pct']}%")
                console.print(f"  Estimated cells to skip  : ~{preview['estimated_total_empty']}")
                console.print(f"  Estimated time saved     : {preview['estimated_time_saved']}\n")
                await scraper.close()
                return 0

            # ── Grid search mode ──────────────────────────────────────────
            if getattr(args, "grid", False):
                console.print(
                    f"[green]Grid search:[/green] cell_size={args.cell_size}km | "
                    f"bounds N={bounds.north:.4f} S={bounds.south:.4f} "
                    f"E={bounds.east:.4f} W={bounds.west:.4f}"
                )
                results = await scraper.scrape_grid(
                    query=queries[0],
                    bounds=bounds,
                    cell_size_km=args.cell_size,
                    max_results_per_cell=args.max_results,
                    adaptive=getattr(args, "adaptive", False),
                    smart_filter=getattr(args, "smart_filter", False),
                    filter_method=getattr(args, "filter_method", "auto"),
                    min_buildings=getattr(args, "min_buildings", 5),
                    on_progress=on_progress,
                )
                total_scraped = len(results)

            # ── Normal mode resume ────────────────────────────────────────
            elif args.resume and len(queries) == 1:
                results = await scraper.scrape(
                    query=queries[0],
                    max_results=args.max_results,
                    resume=True,
                    on_progress=on_progress,
                )
                total_scraped += len(results)

            elif len(queries) == 1:
                results = await scraper.scrape(
                    query=queries[0],
                    max_results=args.max_results,
                    on_progress=on_progress,
                )
                total_scraped += len(results)

            else:
                all_results = await scraper.scrape_multiple(
                    queries=queries,
                    max_results_per_query=args.max_results,
                    on_progress=on_progress,
                )
                total_scraped = sum(len(v) for v in all_results.values())

        finally:
            stats = scraper.get_stats()
            await scraper.close()

    # ----------------------------------------------------------------
    # Summary
    # ----------------------------------------------------------------
    _print_summary(stats, output_dir)
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _interactive_input() -> list[str]:
    """Prompt the user for niche and location(s) and return query strings."""
    console.print(Panel("[bold]Interactive Mode[/bold]\nEnter your search details below."))
    niche = Prompt.ask("[cyan]Business type / niche[/cyan]", default="restaurants")
    location = Prompt.ask("[cyan]City / region[/cyan]", default="Dubai")
    query = f"{niche} in {location}"
    console.print(f"[green]Query:[/green] {query!r}")

    more: list[str] = [query]
    while Confirm.ask("Add another query?", default=False):
        niche2 = Prompt.ask("Business type")
        location2 = Prompt.ask("City / region")
        more.append(f"{niche2} in {location2}")

    return more


def _load_queries_from_file(path_str: str) -> list[str]:
    """Load queries from a CSV or plain-text file."""
    path = Path(path_str)
    if not path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        return []

    queries: list[str] = []
    suffix = path.suffix.lower()

    if suffix == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Support columns: "query" or "niche"+"location"
                if "query" in row and row["query"].strip():
                    queries.append(row["query"].strip())
                elif "niche" in row and "location" in row:
                    queries.append(f"{row['niche'].strip()} in {row['location'].strip()}")
    else:
        # Plain text: one query per line
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    queries.append(line)

    console.print(f"[green]Loaded {len(queries)} queries from {path.name}[/green]")
    return queries


def _print_banner() -> None:
    console.print(Panel(
        f"[bold green]Google Maps Business Leads Scraper[/bold green]\n"
        f"[dim]v{SCRAPER_VERSION} — production-grade lead extraction[/dim]",
        expand=False,
    ))


def _print_summary(stats: dict, output_dir: Path) -> None:
    table = Table(title="Scraping Summary", show_header=False, box=None)
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column(style="white")

    table.add_row("Businesses scraped", str(stats.get("total_scraped", 0)))
    table.add_row("Failed", str(stats.get("total_failed", 0)))
    table.add_row("Duration", stats.get("duration", "—"))
    table.add_row("Output dir", str(output_dir))

    console.print()
    console.print(table)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user. Progress saved — use --resume to continue.[/yellow]")
        sys.exit(0)
