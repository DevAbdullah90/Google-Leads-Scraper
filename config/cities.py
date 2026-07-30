"""
Pre-defined bounding boxes for major cities worldwide.

Used by grid search when the user provides --city or location="Dubai" etc.
Keys are lowercase city names (with common aliases).

BoundingBox(north, south, east, west)
"""

from __future__ import annotations

from scraper.grid import BoundingBox

CITY_BOUNDS: dict[str, BoundingBox] = {
    # ── UAE ─────────────────────────────────────────────────────────────────
    "dubai":          BoundingBox(25.3580, 24.7930, 55.5650, 54.8900),
    "abu dhabi":      BoundingBox(24.5300, 24.3200, 54.5400, 54.2800),
    "abudhabi":       BoundingBox(24.5300, 24.3200, 54.5400, 54.2800),
    "sharjah":        BoundingBox(25.4200, 25.2800, 55.5900, 55.3000),
    "ajman":          BoundingBox(25.4300, 25.3700, 55.5200, 55.4200),
    "ras al khaimah": BoundingBox(25.8500, 25.6500, 55.9800, 55.7200),
    "fujairah":       BoundingBox(25.1700, 25.0800, 56.3900, 56.2800),

    # ── Saudi Arabia ─────────────────────────────────────────────────────────
    "riyadh":         BoundingBox(24.8500, 24.5500, 46.8500, 46.5200),
    "jeddah":         BoundingBox(21.6400, 21.3500, 39.2500, 39.0800),
    "mecca":          BoundingBox(21.4700, 21.3700, 39.8900, 39.7800),
    "medina":         BoundingBox(24.5100, 24.4200, 39.6400, 39.5400),
    "dammam":         BoundingBox(26.4800, 26.3200, 50.1700, 49.9800),

    # ── Kuwait, Qatar, Bahrain, Oman ─────────────────────────────────────────
    "kuwait city":    BoundingBox(29.4200, 29.2800, 48.1000, 47.9000),
    "doha":           BoundingBox(25.3700, 25.2300, 51.5800, 51.4500),
    "manama":         BoundingBox(26.2500, 26.1800, 50.6100, 50.5400),
    "muscat":         BoundingBox(23.6500, 23.5500, 58.6000, 58.4800),

    # ── Egypt ────────────────────────────────────────────────────────────────
    "cairo":          BoundingBox(30.2000, 29.9000, 31.4000, 31.0500),
    "alexandria":     BoundingBox(31.3000, 31.1000, 30.0500, 29.8000),

    # ── Pakistan ─────────────────────────────────────────────────────────────
    "karachi":        BoundingBox(25.0800, 24.7800, 67.2200, 66.8000),
    "lahore":         BoundingBox(31.6800, 31.3800, 74.4500, 74.1500),
    "islamabad":      BoundingBox(33.7800, 33.5800, 73.1800, 72.9000),

    # ── India ────────────────────────────────────────────────────────────────
    "mumbai":         BoundingBox(19.2700, 18.8900, 73.0000, 72.7800),
    "delhi":          BoundingBox(28.8800, 28.4000, 77.3500, 76.8400),
    "new delhi":      BoundingBox(28.8800, 28.4000, 77.3500, 76.8400),
    "bangalore":      BoundingBox(13.1400, 12.8300, 77.7800, 77.4500),
    "bengaluru":      BoundingBox(13.1400, 12.8300, 77.7800, 77.4500),
    "hyderabad":      BoundingBox(17.5300, 17.2700, 78.5900, 78.3200),
    "chennai":        BoundingBox(13.2200, 12.9600, 80.3100, 80.1200),

    # ── UK ───────────────────────────────────────────────────────────────────
    "london":         BoundingBox(51.6860, 51.2860, 0.3340, -0.5100),
    "manchester":     BoundingBox(53.5500, 53.4000, -2.1200, -2.3100),
    "birmingham":     BoundingBox(52.5500, 52.4000, -1.7700, -1.9800),

    # ── USA ───────────────────────────────────────────────────────────────────
    "new york":       BoundingBox(40.9170, 40.4770, -73.7000, -74.2590),
    "los angeles":    BoundingBox(34.3370, 33.7030, -118.1550, -118.6680),
    "chicago":        BoundingBox(42.0230, 41.6440, -87.5240, -87.9400),
    "houston":        BoundingBox(30.1100, 29.5200, -95.0100, -95.7900),
    "miami":          BoundingBox(25.8550, 25.6740, -80.1250, -80.4400),

    # ── Europe ────────────────────────────────────────────────────────────────
    "paris":          BoundingBox(48.9020, 48.8160, 2.4700, 2.2240),
    "berlin":         BoundingBox(52.6750, 52.3380, 13.7610, 13.0883),
    "madrid":         BoundingBox(40.5640, 40.3120, -3.5240, -3.8340),
    "rome":           BoundingBox(41.9960, 41.7960, 12.6160, 12.3540),
    "amsterdam":      BoundingBox(52.4310, 52.3130, 5.0790, 4.7890),
    "istanbul":       BoundingBox(41.1760, 40.8670, 29.2350, 28.7220),

    # ── Asia ──────────────────────────────────────────────────────────────────
    "singapore":      BoundingBox(1.4784, 1.2494, 104.0945, 103.5940),
    "kuala lumpur":   BoundingBox(3.2680, 3.0580, 101.7550, 101.5870),
    "bangkok":        BoundingBox(13.9540, 13.4940, 100.9350, 100.3470),
    "jakarta":        BoundingBox(-6.0920, -6.3720, 107.0000, 106.6820),
    "tokyo":          BoundingBox(35.8170, 35.5230, 139.9200, 139.5710),
    "hong kong":      BoundingBox(22.5610, 22.1780, 114.4060, 113.8260),
    "beijing":        BoundingBox(40.2200, 39.7550, 116.7960, 116.0320),
    "shanghai":       BoundingBox(31.4790, 31.0200, 121.7350, 121.1280),

    # ── Australia ─────────────────────────────────────────────────────────────
    "sydney":         BoundingBox(-33.5780, -34.1740, 151.3430, 150.5200),
    "melbourne":      BoundingBox(-37.5810, -38.1740, 145.5120, 144.5930),

    # ── Canada ────────────────────────────────────────────────────────────────
    "toronto":        BoundingBox(43.8554, 43.5810, -79.1150, -79.6393),
    "vancouver":      BoundingBox(49.3140, 49.1990, -123.0230, -123.2270),
}


def get_city_bounds(city: str) -> BoundingBox | None:
    """
    Look up pre-defined bounds for a city name.
    Case-insensitive, strips extra whitespace.
    Returns None if the city is not in the pre-defined list.
    """
    return CITY_BOUNDS.get(city.lower().strip())


def list_cities() -> list[str]:
    """Return sorted list of all pre-defined city names."""
    return sorted(CITY_BOUNDS.keys())
