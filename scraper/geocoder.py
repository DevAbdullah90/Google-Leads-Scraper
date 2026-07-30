"""
City → BoundingBox resolution.

Resolution order:
  1. JSON geocache (config/geocache.json)   — instant, no network
  2. Pre-defined city bounds (config/cities.py)  — instant, no network
  3. Nominatim (OpenStreetMap) geocoding API     — free, no API key needed
  4. Returns None / raises GeocodingError if all fail

Nominatim usage policy:
  - Must identify the app via User-Agent header
  - Max 1 request/second (enforced in geocode_multiple)
  - No bulk/commercial usage without prior permission
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from config.cities import get_city_bounds
from scraper.grid import BoundingBox

logger = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT    = "GoogleMapsScraper/1.0 (lead-generation-tool)"

# Geocache lives next to cities.py
GEOCACHE_PATH = Path(__file__).parent.parent / "config" / "geocache.json"


# ─────────────────────────────────────────────────────────────────────────────
# Data classes / exceptions
# ─────────────────────────────────────────────────────────────────────────────

class GeocodingError(Exception):
    """Raised when a location cannot be geocoded."""


@dataclass
class GeocodingResult:
    """Full geocoding result returned by geocode()."""
    query: str
    display_name: str
    bounds: BoundingBox
    center_lat: float
    center_lng: float
    location_type: str   # "city", "administrative", "predefined", etc.
    importance: float    # 0.0–1.0

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "display_name": self.display_name,
            "bounds": self.bounds.to_dict(),
            "center_lat": self.center_lat,
            "center_lng": self.center_lng,
            "location_type": self.location_type,
            "importance": self.importance,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Geocache (config/geocache.json)
# ─────────────────────────────────────────────────────────────────────────────

def _cache_key(location: str, country: str | None) -> str:
    return f"{location.lower().strip()}|{(country or '').lower().strip()}"


def _load_geocache() -> dict:
    if GEOCACHE_PATH.exists():
        try:
            return json.loads(GEOCACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_to_geocache(key: str, result: GeocodingResult) -> None:
    try:
        cache = _load_geocache()
        cache[key] = result.to_dict()
        GEOCACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        GEOCACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning("[geocache] Could not save cache entry %r: %s", key, e)


def _get_from_geocache(key: str) -> GeocodingResult | None:
    try:
        cache = _load_geocache()
        if key not in cache:
            return None
        d = cache[key]
        return GeocodingResult(
            query=d["query"],
            display_name=d["display_name"],
            bounds=BoundingBox.from_dict(d["bounds"]),
            center_lat=d["center_lat"],
            center_lng=d["center_lng"],
            location_type=d["location_type"],
            importance=d["importance"],
        )
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Country code helper
# ─────────────────────────────────────────────────────────────────────────────

_COUNTRY_CODES: dict[str, str] = {
    # Middle East
    "united arab emirates": "ae", "uae": "ae",
    "saudi arabia": "sa", "ksa": "sa",
    "kuwait": "kw",
    "qatar": "qa",
    "bahrain": "bh",
    "oman": "om",
    "jordan": "jo",
    "lebanon": "lb",
    "iraq": "iq",
    "iran": "ir",
    "israel": "il",
    "palestine": "ps",
    "syria": "sy",
    "yemen": "ye",
    # Africa
    "egypt": "eg",
    "nigeria": "ng",
    "south africa": "za",
    "kenya": "ke",
    "ghana": "gh",
    "ethiopia": "et",
    "tanzania": "tz",
    "uganda": "ug",
    "morocco": "ma",
    "algeria": "dz",
    "tunisia": "tn",
    "libya": "ly",
    "sudan": "sd",
    "senegal": "sn",
    "cameroon": "cm",
    "angola": "ao",
    "mozambique": "mz",
    "zimbabwe": "zw",
    "zambia": "zm",
    "rwanda": "rw",
    # South Asia
    "pakistan": "pk",
    "india": "in",
    "bangladesh": "bd",
    "sri lanka": "lk",
    "nepal": "np",
    "maldives": "mv",
    "afghanistan": "af",
    # Southeast Asia
    "singapore": "sg",
    "malaysia": "my",
    "thailand": "th",
    "indonesia": "id",
    "philippines": "ph",
    "vietnam": "vn",
    "cambodia": "kh",
    "myanmar": "mm",
    "laos": "la",
    "brunei": "bn",
    "timor-leste": "tl",
    # East Asia
    "japan": "jp",
    "china": "cn",
    "hong kong": "hk",
    "taiwan": "tw",
    "south korea": "kr", "korea": "kr",
    "north korea": "kp",
    "mongolia": "mn",
    # Central Asia
    "kazakhstan": "kz",
    "uzbekistan": "uz",
    "turkmenistan": "tm",
    "kyrgyzstan": "kg",
    "tajikistan": "tj",
    # Europe
    "united kingdom": "gb", "uk": "gb", "great britain": "gb", "england": "gb",
    "germany": "de",
    "france": "fr",
    "spain": "es",
    "italy": "it",
    "netherlands": "nl",
    "turkey": "tr",
    "russia": "ru",
    "ukraine": "ua",
    "poland": "pl",
    "sweden": "se",
    "norway": "no",
    "denmark": "dk",
    "finland": "fi",
    "switzerland": "ch",
    "austria": "at",
    "belgium": "be",
    "portugal": "pt",
    "greece": "gr",
    "czech republic": "cz", "czechia": "cz",
    "hungary": "hu",
    "romania": "ro",
    "bulgaria": "bg",
    "croatia": "hr",
    "serbia": "rs",
    "slovakia": "sk",
    "slovenia": "si",
    "ireland": "ie",
    "scotland": "gb",
    "wales": "gb",
    "luxembourg": "lu",
    "malta": "mt",
    "cyprus": "cy",
    "iceland": "is",
    "albania": "al",
    "north macedonia": "mk",
    "bosnia": "ba",
    "montenegro": "me",
    "moldova": "md",
    "latvia": "lv",
    "lithuania": "lt",
    "estonia": "ee",
    "belarus": "by",
    "georgia": "ge",
    "armenia": "am",
    "azerbaijan": "az",
    # Americas
    "united states": "us", "usa": "us", "united states of america": "us",
    "canada": "ca",
    "mexico": "mx",
    "brazil": "br",
    "argentina": "ar",
    "colombia": "co",
    "chile": "cl",
    "peru": "pe",
    "venezuela": "ve",
    "ecuador": "ec",
    "bolivia": "bo",
    "paraguay": "py",
    "uruguay": "uy",
    "cuba": "cu",
    "dominican republic": "do",
    "puerto rico": "pr",
    "jamaica": "jm",
    "haiti": "ht",
    "panama": "pa",
    "costa rica": "cr",
    "guatemala": "gt",
    "honduras": "hn",
    "el salvador": "sv",
    "nicaragua": "ni",
    # Oceania
    "australia": "au",
    "new zealand": "nz",
    "fiji": "fj",
    "papua new guinea": "pg",
}


def _get_country_code(country: str) -> str | None:
    key = country.lower().strip()
    if len(key) == 2:
        return key  # already an ISO code
    return _COUNTRY_CODES.get(key)


# ─────────────────────────────────────────────────────────────────────────────
# Nominatim (internal)
# ─────────────────────────────────────────────────────────────────────────────

_NOMINATIM_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept-Language": "en",          # always return English names
}


def _best_hit(data: list[dict]) -> dict | None:
    """Return the highest-importance result that has a bounding box."""
    candidates = [h for h in data if h.get("boundingbox") and len(h["boundingbox"]) == 4]
    if not candidates:
        return None
    return max(candidates, key=lambda h: float(h.get("importance", 0)))


async def _nominatim_full(query: str, country_code: str | None) -> GeocodingResult | None:
    """
    Query Nominatim for any location (city, district, country, region, POI).

    Returns the highest-importance result that has a bounding box, or None.
    No featuretype restriction — works for countries, states, neighbourhoods, etc.
    """
    params: dict = {
        "q": query,
        "format": "json",
        "limit": 5,           # fetch several, pick best by importance
        "addressdetails": 0,  # not needed, saves bandwidth
    }
    if country_code:
        params["countrycodes"] = country_code

    try:
        async with httpx.AsyncClient(
            headers=_NOMINATIM_HEADERS,
            timeout=15.0,
        ) as client:
            resp = await client.get(_NOMINATIM_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        logger.debug("[geocoder/nominatim] %d result(s) for %r", len(data), query)

        hit = _best_hit(data)
        if hit is None:
            return None

        bb = hit["boundingbox"]  # [south, north, west, east]
        south, north, west, east = float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])
        bounds = BoundingBox(north=north, south=south, east=east, west=west)

        return GeocodingResult(
            query=query,
            display_name=hit.get("display_name", query),
            bounds=bounds,
            center_lat=float(hit.get("lat", (north + south) / 2)),
            center_lng=float(hit.get("lon", (east + west) / 2)),
            location_type=hit.get("type", "unknown"),
            importance=float(hit.get("importance", 0.5)),
        )

    except httpx.TimeoutException:
        logger.warning("[geocoder/nominatim] Timed out for %r", query)
    except httpx.HTTPStatusError as e:
        logger.warning("[geocoder/nominatim] HTTP %s for %r", e.response.status_code, query)
    except Exception as e:
        logger.warning("[geocoder/nominatim] Error for %r: %s", query, e)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API — new (geocode / get_bounds / geocode_multiple)
# ─────────────────────────────────────────────────────────────────────────────

async def geocode(
    location: str,
    country: Optional[str] = None,
    use_cache: bool = True,
) -> GeocodingResult:
    """
    Convert any location name to a GeocodingResult (with bounding box).

    Works for anything Nominatim knows: POI, neighbourhood, district, city,
    state/province, country, continent, or region — no hard-coded list needed.

    Resolution order:
      1. geocache.json            — instant, no network
      2. config/cities.py         — instant, no network (popular cities)
      3. Nominatim (OSM)          — free, no API key, worldwide coverage
         a. with ISO country-code hint for precision
         b. with "{location}, {country}" as a plain-text query

    Raises:
        GeocodingError: If all methods fail.
    """
    key = _cache_key(location, country)
    logger.info("[geocoder] Geocoding %r (country=%r)…", location, country)

    # ── 1. Cache ───────────────────────────────────────────────────────────
    if use_cache:
        cached = _get_from_geocache(key)
        if cached:
            logger.debug("[geocoder] Cache hit for %r", location)
            return cached

    # ── 2. Pre-defined bounds ─────────────────────────────────────────────
    predefined = get_city_bounds(location)
    if predefined:
        result = GeocodingResult(
            query=location,
            display_name=location.title(),
            bounds=predefined,
            center_lat=predefined.center_lat,
            center_lng=predefined.center_lng,
            location_type="city",
            importance=1.0,
        )
        logger.info("[geocoder] Resolved %r from pre-defined bounds", location)
        _save_to_geocache(key, result)
        return result

    # ── 3. Nominatim with country code ────────────────────────────────────
    cc = _get_country_code(country) if country else None
    result = await _nominatim_full(location, cc)

    # ── 4. Nominatim with appended country ────────────────────────────────
    if result is None and country:
        result = await _nominatim_full(f"{location}, {country}", None)

    if result:
        logger.info(
            "[geocoder] Nominatim resolved %r → %s | type=%s | area=%.1f km²",
            location, result.display_name, result.location_type,
            result.bounds.width_km * result.bounds.height_km,
        )
        _save_to_geocache(key, result)
        return result

    logger.warning(
        "[geocoder] Could not resolve %r via Nominatim. "
        "Try a more specific name (e.g. 'Dubai, UAE') or use --bounds directly.",
        location,
    )
    raise GeocodingError(
        f"Could not geocode {location!r}. "
        "Try a more specific name (e.g. 'Dubai, UAE') or pass --bounds N,S,E,W."
    )


async def get_bounds(
    location: str,
    country: Optional[str] = None,
) -> BoundingBox:
    """Convenience wrapper — returns just the BoundingBox for a location."""
    result = await geocode(location, country)
    return result.bounds


async def geocode_multiple(
    locations: list[str],
    country: Optional[str] = None,
    delay_seconds: float = 1.1,
) -> dict[str, Optional[GeocodingResult]]:
    """
    Geocode a list of locations sequentially with Nominatim rate limiting.

    Args:
        locations:      List of location names.
        country:        Optional country hint applied to all locations.
        delay_seconds:  Delay between API calls (Nominatim: 1 req/sec).

    Returns:
        Dict mapping location → GeocodingResult (or None if failed).
    """
    results: dict[str, Optional[GeocodingResult]] = {}
    for i, loc in enumerate(locations):
        try:
            results[loc] = await geocode(loc, country)
        except GeocodingError:
            logger.warning("[geocoder] Failed to geocode %r — skipping.", loc)
            results[loc] = None
        if i < len(locations) - 1:
            await asyncio.sleep(delay_seconds)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Legacy API — kept for backward compatibility
# ─────────────────────────────────────────────────────────────────────────────

async def resolve_bounds(city: str, country: str | None = None) -> BoundingBox | None:
    """
    Resolve a city name to a BoundingBox.

    Kept for backward compatibility. New code should use geocode() or get_bounds().

    Returns:
        BoundingBox if resolved, None if not found.
    """
    try:
        return await get_bounds(city, country)
    except GeocodingError:
        return None
