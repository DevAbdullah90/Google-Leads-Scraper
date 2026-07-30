"""
Shared utilities: logging infrastructure, delays, proxy parsing, text helpers.

Logging architecture
--------------------
- Root logger: "scraper"  (configured once here with file + console handlers)
- Child loggers: logging.getLogger(__name__) in every module
  e.g. scraper.extractor, scraper.browser, scraper.api …
  They inherit handlers/level from root automatically.

Console format  → timestamp  level  module-name  message
File format     → timestamp  level  module:function:line  message
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import logging.handlers
import random
import re
import time
from pathlib import Path
from typing import Any, Generator

from config.settings import (
    ACTION_DELAY_MAX,
    ACTION_DELAY_MIN,
    LOG_BACKUP_COUNT,
    LOG_LEVEL,
    LOG_MAX_BYTES,
    LOGS_DIR,
    MAX_DELAY,
    MIN_DELAY,
    USER_AGENTS_FILE,
)


# ============================================================
# Logger setup
# ============================================================

def setup_logging(*, debug: bool = False) -> logging.Logger:
    """
    Configure the root 'scraper' logger with a rotating file handler and a
    console handler.  Call once at application startup.  Subsequent calls are
    no-ops (handlers are not duplicated).

    Child loggers (logging.getLogger(__name__) in each module) inherit
    configuration automatically.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("scraper")
    if root.handlers:
        return root  # Already configured — don't add duplicate handlers

    level = logging.DEBUG if debug else getattr(logging, LOG_LEVEL, logging.INFO)
    root.setLevel(logging.DEBUG)  # Root always DEBUG; handlers filter by level

    # ── Console handler ──────────────────────────────────────────────────────
    # Format:  12:34:56 [INFO    ] scraper.api               — message
    console_fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)-28s — %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(console_fmt)

    # ── Rotating file handler ────────────────────────────────────────────────
    # Format:  2024-01-01 12:34:56 [INFO    ] scraper.api:scrape:142 — message
    file_fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s:%(funcName)s:%(lineno)d — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = logging.handlers.RotatingFileHandler(
        LOGS_DIR / "scraper.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)  # File always captures DEBUG
    file_handler.setFormatter(file_fmt)

    root.addHandler(console_handler)
    root.addHandler(file_handler)

    root.info("Logging initialised — level=%s | file=%s/scraper.log",
              logging.getLevelName(level), LOGS_DIR)
    return root


def enable_debug() -> None:
    """Switch console handler to DEBUG (called when --debug flag is set)."""
    root = logging.getLogger("scraper")
    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.handlers.RotatingFileHandler
        ):
            handler.setLevel(logging.DEBUG)
    root.debug("Debug logging enabled.")


# Auto-configure when this module is first imported
setup_logging()

# Module-level logger (used only for utils itself)
logger = logging.getLogger(__name__)


# ============================================================
# Visual helpers — make logs scannable at a glance
# ============================================================

def log_section(log: logging.Logger, title: str, *, width: int = 60, char: str = "═") -> None:
    """Print a prominent section banner to the log."""
    log.info(char * width)
    log.info("  %s", title)
    log.info(char * width)


def log_subsection(log: logging.Logger, title: str, *, width: int = 55, char: str = "─") -> None:
    """Print a lighter subsection separator."""
    log.debug("%s %s", char * 3, title)


def log_field(
    log: logging.Logger,
    field: str,
    value: Any,
    *,
    selector: str | None = None,
    raw: Any = None,
) -> None:
    """
    Log a single extracted field in a consistent, scannable format.

    ✓ field_name     = <value>           [via 'selector']
    ✗ field_name     = (not found)
    """
    col = f"%-20s" % field
    if value is not None:
        sel_part = f"  [via {selector!r}]" if selector else ""
        raw_part = f"  (raw: {raw!r})" if raw is not None and raw != value else ""
        log.debug("  ✓ %s = %r%s%s", col, value, sel_part, raw_part)
    else:
        log.debug("  ✗ %s = (not found)", col)


def log_selector_attempt(log: logging.Logger, field: str, selector: str, found: bool) -> None:
    """Log a single selector attempt at TRACE-level detail."""
    mark = "✓" if found else "·"
    log.debug("     %s [%s] tried selector: %s", mark, field, selector)


# ============================================================
# Timing context manager
# ============================================================

@contextlib.asynccontextmanager
async def timed_op(log: logging.Logger, operation: str):
    """
    Async context manager that logs how long an operation took.

    Usage:
        async with timed_op(logger, "Navigate to business page"):
            await page.goto(url)
    """
    start = time.monotonic()
    log.debug("  ▶ %s …", operation)
    try:
        yield
        elapsed = time.monotonic() - start
        log.debug("  ✓ %s — done in %.2fs", operation, elapsed)
    except Exception as exc:
        elapsed = time.monotonic() - start
        log.debug("  ✗ %s — FAILED after %.2fs: %s", operation, elapsed, exc)
        raise


# ============================================================
# Delays
# ============================================================

async def random_delay(min_sec: float = MIN_DELAY, max_sec: float = MAX_DELAY) -> None:
    """Sleep for a random human-like duration."""
    delay = random.uniform(min_sec, max_sec)
    logger.debug("Sleeping %.1fs (human-like delay) …", delay)
    await asyncio.sleep(delay)


async def action_delay() -> None:
    """Short delay between in-page actions."""
    delay = random.uniform(ACTION_DELAY_MIN, ACTION_DELAY_MAX)
    await asyncio.sleep(delay)


# ============================================================
# User agents
# ============================================================

_user_agents: list[str] | None = None

_DEFAULT_USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]


def _load_user_agents() -> list[str]:
    try:
        if USER_AGENTS_FILE.exists():
            lines = USER_AGENTS_FILE.read_text(encoding="utf-8").splitlines()
            agents = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
            if agents:
                logger.debug("Loaded %d user agents from %s", len(agents), USER_AGENTS_FILE)
                return agents
    except Exception as e:
        logger.warning("Could not load user agents from file: %s — using defaults", e)
    logger.debug("Using %d default user agents", len(_DEFAULT_USER_AGENTS))
    return _DEFAULT_USER_AGENTS


def random_user_agent() -> str:
    global _user_agents
    if _user_agents is None:
        _user_agents = _load_user_agents()
    ua = random.choice(_user_agents)
    return ua


# ============================================================
# Proxy parsing
# ============================================================

def parse_proxy(proxy_str: str) -> dict[str, str]:
    """
    Parse a proxy string in any common format into a Playwright proxy dict.

    Supported formats:
      host:port
      http://host:port
      http://user:pass@host:port
      user:pass@host:port
      socks5://host:port
      socks5://user:pass@host:port
    """
    proxy_str = proxy_str.strip()
    result: dict[str, str] = {}

    if "://" in proxy_str:
        scheme, rest = proxy_str.split("://", 1)
    else:
        scheme, rest = "http", proxy_str

    if "@" in rest:
        auth_part, host_part = rest.rsplit("@", 1)
        if ":" in auth_part:
            username, password = auth_part.split(":", 1)
            result["username"] = username
            result["password"] = "***"  # Never log real password
            result["_password"] = password  # Internal use only
        else:
            result["username"] = auth_part
            result["_password"] = ""
    else:
        host_part = rest

    result["server"] = f"{scheme}://{host_part}"
    logger.debug(
        "Proxy parsed: server=%s  auth=%s",
        result["server"],
        f"user={result['username']!r}" if "username" in result else "none",
    )

    # Return Playwright-compatible dict (without our internal _password alias)
    pw_dict = {"server": result["server"]}
    if "username" in result:
        pw_dict["username"] = result["username"]
        pw_dict["password"] = result.get("_password", "")
    return pw_dict


# ============================================================
# Text helpers
# ============================================================

_WHITESPACE_RE = re.compile(r"\s+")


def clean_text(text: str | None) -> str | None:
    """Strip and normalise internal whitespace. Returns None for empty strings."""
    if not text:
        return None
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text or None


def format_duration(seconds: float) -> str:
    """Convert elapsed seconds to a human-readable string (s / m / h / d / w / mo)."""
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    hours, rem    = divmod(total, 3600)
    mins          = rem // 60
    days, hours   = divmod(hours, 24)
    months, days  = divmod(days, 30)
    years, months = divmod(months, 12)
    if years:
        return f"{years}yr {months}mo {days}d {hours}h {mins}m"
    if months:
        return f"{months}mo {days}d {hours}h {mins}m"
    weeks, days = divmod(days, 7)
    if weeks:
        return f"{weeks}w {days}d {hours}h {mins}m"
    if days:
        return f"{days}d {hours}h {mins}m"
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """Make a string safe to use as a filename component."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name[:max_len] if name else "unnamed"
