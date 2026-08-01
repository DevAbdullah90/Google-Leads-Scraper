"""
Infinite-scroll handling for the Google Maps results panel.

Log coverage:
 - Feed detection (which selector matched)
 - Each scroll iteration: how many new URLs were found, running total
 - Which result-link selector was productive
 - End-of-results detection method (text / selector / no-new-streak)
 - Final URL count and stop reason
"""

from __future__ import annotations

import asyncio
import logging
import random
import time

from playwright.async_api import Page

from config.selectors import (
    END_OF_RESULTS_SELECTORS,
    END_OF_RESULTS_TEXT,
    RESULT_LINK_SELECTORS,
    RESULTS_FEED_SELECTORS,
)
from config.settings import MAX_SCROLL_ATTEMPTS, SCROLL_PAUSE_MAX, SCROLL_PAUSE_MIN
from scraper.utils import log_subsection

logger = logging.getLogger(__name__)


def _is_url_in_skipped(href: str, skipped_urls: set[str]) -> bool:
    """Return True if href or its Place ID exists in skipped_urls."""
    if not skipped_urls or not href:
        return False
    if href in skipped_urls:
        return True
    import re
    m = re.search(r"(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)", href)
    if m and m.group(1) in skipped_urls:
        return True
    return False


async def collect_business_urls(
    page: Page,
    max_results: int | None = None,
    skipped_urls: set[str] | None = None,
) -> list[str]:
    """
    Scroll the Google Maps results panel until all results are loaded
    (or `max_results` is reached) and return deduplicated business URLs.

    Args:
        page: Active Playwright page already on a Google Maps search URL.
        max_results: Stop after collecting this many URLs (None = all).
        skipped_urls: Set of URLs/Place IDs already scraped in Google Sheet to skip.

    Returns:
        List of unique Google Maps place URLs.
    """
    start_time = time.monotonic()

    logger.info("Starting result collection (max_results=%s, max_scroll_attempts=%d)",
                max_results or "unlimited", MAX_SCROLL_ATTEMPTS)

    # ── Locate the results feed ───────────────────────────────────────────────
    feed = await _wait_for_feed(page)
    if feed is None:
        logger.error(
            "Results feed NOT FOUND — tried %d selectors: %s",
            len(RESULTS_FEED_SELECTORS),
            RESULTS_FEED_SELECTORS,
        )
        logger.error(
            "Possible causes: page didn't load, Google layout changed, "
            "or the search returned zero results."
        )
        return []

    # ── Scroll loop ───────────────────────────────────────────────────────────
    urls: list[str] = []
    seen: set[str] = set()
    no_new_streak = 0
    max_no_new = 10 if skipped_urls else 5
    active_link_selector: str | None = None
    stop_reason = "max_scroll_attempts"
    total_skipped_sheet = 0

    for attempt in range(1, MAX_SCROLL_ATTEMPTS + 1):

        # Collect links using the first selector that works
        new_count = 0
        new_seen_count = 0
        link_selector_used: str | None = None

        for selector in RESULT_LINK_SELECTORS:
            try:
                links = await page.query_selector_all(selector)
                if not links:
                    continue
                for link in links:
                    try:
                        href = await link.get_attribute("href")
                        if href and "/maps/place/" in href and href not in seen:
                            seen.add(href)
                            new_seen_count += 1
                            if skipped_urls and _is_url_in_skipped(href, skipped_urls):
                                total_skipped_sheet += 1
                                logger.debug("Skipping URL already in Google Sheet: %s", href[:70])
                                continue
                            urls.append(href)
                            new_count += 1
                    except Exception:
                        continue
                link_selector_used = selector
                break  # Use the first selector that found results
            except Exception as e:
                logger.debug("  Link selector %r failed: %s", selector, e)
                continue

        if link_selector_used and active_link_selector != link_selector_used:
            active_link_selector = link_selector_used
            logger.debug("Active result-link selector: %r", link_selector_used)

        # Reset streak if Google Maps is actively producing new cards (even if skipped)
        if new_seen_count > 0:
            no_new_streak = 0
            logger.debug(
                "Scroll %3d/%d | +%2d fresh, +%2d cards seen | total_fresh=%d (skipped_sheet=%d) | selector=%r",
                attempt, MAX_SCROLL_ATTEMPTS, new_count, new_seen_count, len(urls), total_skipped_sheet,
                link_selector_used or "none",
            )
        else:
            no_new_streak += 1
            logger.debug(
                "Scroll %3d/%d | +0 cards | total_fresh=%d (skipped_sheet=%d) | no-new streak=%d/%d",
                attempt, MAX_SCROLL_ATTEMPTS, len(urls), total_skipped_sheet, no_new_streak, max_no_new,
            )

        # ── Check stop conditions ─────────────────────────────────────────────

        if max_results and len(urls) >= max_results:
            stop_reason = f"max_results ({max_results}) reached"
            break

        if await _is_end_of_results(page):
            stop_reason = "end-of-list indicator detected"
            break

        if no_new_streak >= max_no_new:
            stop_reason = f"no new URLs for {no_new_streak} consecutive scrolls"
            break

        # ── Scroll the feed ───────────────────────────────────────────────────
        scroll_px = random.randint(600, 1200)
        await _scroll_feed(page, feed, scroll_px)
        pause = random.uniform(SCROLL_PAUSE_MIN, SCROLL_PAUSE_MAX)
        logger.debug("  Scrolled %dpx, pausing %.1fs…", scroll_px, pause)
        await asyncio.sleep(pause)

    elapsed = time.monotonic() - start_time
    result = urls[:max_results] if max_results else urls

    if total_skipped_sheet > 0:
        logger.info("[scroll] Skipped %d URLs already in Google Sheet during scrolling ✓", total_skipped_sheet)

    logger.info(
        "Collection complete: %d fresh URLs in %.1fs | stop reason: %s",
        len(result), elapsed, stop_reason,
    )
    if len(result) == 0:
        logger.warning(
            "Zero URLs collected — check if Google Maps returned results "
            "for this query, and verify RESULTS_FEED_SELECTORS are current."
        )

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _wait_for_feed(page: Page, timeout: int = 15_000):
    """Wait for the results feed to appear. Returns the element or None."""
    logger.debug("Waiting for results feed (timeout=%dms)…", timeout)
    for selector in RESULTS_FEED_SELECTORS:
        try:
            logger.debug("  Trying feed selector: %r", selector)
            await page.wait_for_selector(selector, timeout=timeout)
            el = await page.query_selector(selector)
            if el:
                logger.debug("  Feed found via: %r ✓", selector)
                return el
        except Exception as e:
            logger.debug("  Feed selector %r timed out or errored: %s", selector, e)
    return None


async def _scroll_feed(page: Page, feed, scroll_px: int) -> None:
    """Scroll the feed element. Falls back to window scroll on error."""
    try:
        await feed.evaluate(f"el => el.scrollBy(0, {scroll_px})")
    except Exception as e:
        logger.debug("Feed scroll failed (%s) — falling back to window.scrollBy", e)
        try:
            await page.evaluate(f"window.scrollBy(0, {scroll_px})")
        except Exception as e2:
            logger.debug("Window scroll also failed: %s", e2)


async def _is_end_of_results(page: Page) -> bool:
    """Return True when Google signals no more results are available."""

    # Check for known end-of-results text strings
    for text in END_OF_RESULTS_TEXT:
        try:
            el = await page.query_selector(f'text="{text}"')
            if el:
                logger.debug("End-of-results text matched: %r", text)
                return True
        except Exception:
            pass

    # Check for known end-of-results element selectors
    for selector in END_OF_RESULTS_SELECTORS:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                content = await el.inner_text()
                if content and any(t.lower() in content.lower() for t in END_OF_RESULTS_TEXT):
                    logger.debug(
                        "End-of-results selector %r matched with text: %r",
                        selector, content[:80],
                    )
                    return True
        except Exception:
            continue

    return False
