"""
Google Maps Scraper — public API surface.

from scraper import GoogleMapsScraper, scrape_leads, scrape_leads_bulk, scrape_leads_sync
from scraper import scrape_leads_grid
from scraper import geocode, get_bounds, GeocodingResult
"""

from scraper.api import (
    GoogleMapsScraper,
    scrape_leads,
    scrape_leads_bulk,
    scrape_leads_grid,
    scrape_leads_sync,
)
from scraper.geocoder import GeocodingResult, GeocodingError, geocode, get_bounds, geocode_multiple
from scraper.grid import BoundingBox, Grid, GridCell, make_grid, calculate_optimal_cell_size

__all__ = [
    # API
    "GoogleMapsScraper",
    "scrape_leads",
    "scrape_leads_bulk",
    "scrape_leads_grid",
    "scrape_leads_sync",
    # Geocoding
    "geocode",
    "get_bounds",
    "geocode_multiple",
    "GeocodingResult",
    "GeocodingError",
    # Grid
    "BoundingBox",
    "Grid",
    "GridCell",
    "make_grid",
    "calculate_optimal_cell_size",
]
