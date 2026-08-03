"""Global settings and configuration for the Google Maps scraper."""

from __future__ import annotations

import os
from pathlib import Path

# === PATHS ===
BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
PROGRESS_FILE = BASE_DIR / "progress.json"
PROXIES_FILE = BASE_DIR / "proxies.txt"
USER_AGENTS_FILE = BASE_DIR / "user_agents.txt"
GOOGLE_SESSION_FILE = DATA_DIR / "google_session.json"   # created by save_google_session.py

# Ensure required directories exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# === DATABASE ===
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{DATA_DIR / 'leads.db'}",
)

# === BROWSER ===
HEADLESS: bool = True
BROWSER_RESTART_AFTER: int = 100  # Restart browser every N businesses

# Randomized viewport bounds (min, max)
VIEWPORT_WIDTH_RANGE: tuple[int, int] = (1280, 1920)
VIEWPORT_HEIGHT_RANGE: tuple[int, int] = (768, 1080)

# === DELAYS (seconds) ===
MIN_DELAY: float = 2.0           # reduced from 3.0 — still human-like, less dead time
MAX_DELAY: float = 4.0           # reduced from 6.0

# Short delay between actions within a page
ACTION_DELAY_MIN: float = 0.3    # reduced from 0.5
ACTION_DELAY_MAX: float = 0.8    # reduced from 1.5

# Long break after N businesses
LONG_BREAK_INTERVAL: int = 40    # reduced from 20 — one break per 50-biz run instead of two
LONG_BREAK_MIN: float = 15.0     # reduced from 30.0
LONG_BREAK_MAX: float = 30.0     # reduced from 60.0

# Scroll pause
SCROLL_PAUSE_MIN: float = 0.7    # reduced from 1.0
SCROLL_PAUSE_MAX: float = 1.5    # reduced from 2.5

# === RETRY ===
MAX_RETRIES: int = 3             # reduced from 5 — 1s+2s+4s=7s max vs 31s; structural failures don't benefit from 5 retries
RETRY_BASE_DELAY: float = 2.0  # Exponential backoff base

# === SCRAPING LIMITS ===

DEFAULT_MAX_RESULTS: int | None = None  # None = unlimited
MAX_SCROLL_ATTEMPTS: int = 150  # Safety cap on scroll iterations
PAGE_LOAD_TIMEOUT: int = 30_000  # ms
ELEMENT_WAIT_TIMEOUT: int = 10_000  # ms

# === EMAIL EXTRACTION ===
EMAIL_TIMEOUT: float = 20.0  # 20s allows JS-heavy site rendering (Elementor/Wix/Single Page Apps)
EMAIL_COMMON_PATHS: list[str] = [
    "/contact",
    "/contact-us",
    "/contactus",
    "/contact-me",
    "/about",
    "/about-us",
    "/team",
    "/our-team",
    "/get-in-touch",
    "/reach-us",
    "/connect",
    "/privacy",
    "/privacy-policy",
    "/impressum",
]
MAX_EMAIL_PAGES: int = 6  # homepage + top 5 sub-pages

# Pages to scan for social media links in addition to homepage
SOCIAL_SCAN_PATHS: list[str] = [
    "/contact",
    "/contact-us",
    "/about",
    "/about-us",
]

# === REVIEWS ===
MAX_REVIEWS_SAMPLE: int = 5  # Reviews to extract per business

# === IMAGES ===
MAX_IMAGES: int = 10  # Max image URLs to extract

# === LOGGING ===
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT: int = 5

# === GOOGLE MAPS ===
GOOGLE_MAPS_SEARCH_URL: str = "https://www.google.com/maps/search/{query}"
GOOGLE_MAPS_BASE_URL: str = "https://www.google.com"

# === GOOGLE SHEETS ===
GOOGLE_SHEETS_SPREADSHEET_ID: str = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
GOOGLE_SHEETS_URL: str = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEETS_SPREADSHEET_ID}/edit" if GOOGLE_SHEETS_SPREADSHEET_ID else ""

# === SCRAPER VERSION ===
SCRAPER_VERSION: str = "1.0.0"
