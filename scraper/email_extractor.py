"""
Email extraction from business websites.

Strategy:
  1. Use prefetched_html if caller already fetched the homepage (shared with social extractor)
  2. httpx (fast, concurrent) — homepage + common contact pages scanned in parallel
  3. Playwright fallback     — for JS-heavy sites that httpx can't read

Log coverage:
 - Every URL attempted (method, status code, response size)
 - How many raw email candidates found on each page
 - Which page the accepted email came from
 - Why httpx was skipped and Playwright fallback triggered
 - Final result per website
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from urllib.parse import urljoin

import httpx
from playwright.async_api import Page

from config.settings import EMAIL_COMMON_PATHS, EMAIL_TIMEOUT, MAX_EMAIL_PAGES, SOCIAL_SCAN_PATHS
from scraper.utils import random_user_agent
from scraper.validator import find_emails_in_text, validate_email

logger = logging.getLogger(__name__)

_MAILTO_RE = re.compile(
    r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})',
    re.IGNORECASE,
)

_HTTPX_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ─────────────────────────────────────────────────────────────────────────────
# Shared homepage fetch (called once per business, result passed to both
# email and social extractors — avoids fetching the same URL twice)
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_homepage_html(website_url: str) -> str | None:
    """
    Fetch and return the homepage HTML for a business website.

    Called once per business in extractor.py so that both email_extractor and
    social_extractor can share the result instead of each making a separate request.
    Returns None on any network error or timeout.
    """
    if not website_url:
        return None
    try:
        async with httpx.AsyncClient(
            headers={**_HTTPX_HEADERS, "User-Agent": random_user_agent()},
            timeout=EMAIL_TIMEOUT,
            follow_redirects=True,
            verify=False,
        ) as client:
            resp = await client.get(website_url)
            if len(resp.content) > 5 * 1024 * 1024:
                logger.warning(
                    "[website] Prefetch response too large (%.1f KB) — skipping %s",
                    len(resp.content) / 1024, website_url,
                )
                return None
            if resp.status_code < 400:
                logger.debug(
                    "[website] Prefetched homepage %s → %d (%.1f KB)",
                    website_url, resp.status_code, len(resp.content) / 1024,
                )
                return resp.text
            logger.debug(
                "[website] Prefetch returned HTTP %d for %s — no HTML cached",
                resp.status_code, website_url,
            )
    except httpx.ConnectError as e:
        logger.debug("[website] Cannot connect to %s: %s", website_url, e)
    except httpx.TimeoutException:
        logger.debug("[website] Timeout prefetching %s (limit=%.1fs)", website_url, EMAIL_TIMEOUT)
    except Exception as e:
        logger.debug("[website] Unexpected error prefetching %s: %s", website_url, e)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

async def extract_email(
    website_url: str,
    page: Page | None = None,
    *,
    prefetched_html: str | None = None,
) -> str | None:
    """
    Attempt to find a business email from the given website.

    Args:
        website_url:     The business website URL.
        page:            Playwright page for JS-heavy fallback (optional).
        prefetched_html: Homepage HTML already fetched by fetch_homepage_html().
                         When provided, skips the homepage HTTP request entirely.

    Tries prefetched/httpx first; falls back to Playwright if the site is
    unreachable via httpx or if all httpx pages return nothing.
    """
    if not website_url:
        logger.debug("[email] No website URL provided — skipping")
        return None

    logger.debug("[email] Starting extraction for: %s", website_url)
    start = time.monotonic()

    email = await _extract_via_httpx(website_url, prefetched_html=prefetched_html)

    if email:
        logger.info("[email] Found via httpx in %.1fs: %s", time.monotonic() - start, email)
        return email

    if page is not None:
        logger.debug("[email] httpx found nothing — trying Playwright fallback…")
        email = await _extract_via_playwright(page, website_url)
        if email:
            logger.info(
                "[email] Found via Playwright in %.1fs: %s",
                time.monotonic() - start, email,
            )
        else:
            logger.debug("[email] Playwright fallback also found nothing.")
    else:
        logger.debug("[email] No Playwright page available for fallback.")

    if not email:
        logger.debug("[email] No email found for %s (%.1fs)", website_url, time.monotonic() - start)

    return email


# ─────────────────────────────────────────────────────────────────────────────
# httpx path
# ─────────────────────────────────────────────────────────────────────────────

async def _extract_via_httpx(
    base_url: str,
    prefetched_html: str | None = None,
) -> str | None:
    """
    Scan homepage + common sub-pages using httpx.

    If prefetched_html is provided, the homepage is already scanned — only
    sub-pages are fetched (saving one full HTTP round-trip).
    Sub-pages are fetched in parallel for speed.
    """
    # ── Step 1: try prefetched homepage HTML first ────────────────────────────
    if prefetched_html:
        email = _find_email_in_html(prefetched_html, source="homepage (prefetched)")
        if email:
            return email
        logger.debug("[email/httpx] Prefetched HTML had no email — trying sub-pages…")
        # Homepage already counted as page 1
        pages_already_tried = 1
    else:
        pages_already_tried = 0

    # ── Step 2: fetch remaining sub-pages ────────────────────────────────────
    remaining_slots = MAX_EMAIL_PAGES - pages_already_tried
    if remaining_slots <= 0:
        logger.debug("[email/httpx] No sub-page slots remaining after homepage")
        return None

    sub_paths = EMAIL_COMMON_PATHS[:remaining_slots]
    logger.debug(
        "[email/httpx] Scanning %d sub-pages in parallel for %s…",
        len(sub_paths), base_url,
    )

    try:
        async with httpx.AsyncClient(
            headers={**_HTTPX_HEADERS, "User-Agent": random_user_agent()},
            timeout=EMAIL_TIMEOUT,
            follow_redirects=True,
            verify=False,
        ) as client:

            # If no prefetched HTML, fetch homepage first (sequential — need to
            # confirm site is reachable before firing parallel sub-page requests)
            if not prefetched_html:
                try:
                    resp = await client.get(base_url)
                    size_kb = len(resp.content) / 1024
                    logger.debug(
                        "[email/httpx] GET %s → %d (%.1f KB)",
                        base_url, resp.status_code, size_kb,
                    )
                    if len(resp.content) > 5 * 1024 * 1024:
                        logger.warning("[email/httpx] Response too large (%.1f KB) — skipping %s", size_kb, base_url)
                        return None
                    if resp.status_code < 400:
                        email = _find_email_in_html(resp.text, source="homepage")
                        if email:
                            return email
                    else:
                        logger.debug(
                            "[email/httpx] Homepage returned HTTP %d — skipping sub-pages",
                            resp.status_code,
                        )
                        return None
                except httpx.ConnectError as e:
                    logger.debug(
                        "[email/httpx] Cannot connect to %s: %s — skipping all pages",
                        base_url, e,
                    )
                    return None
                except httpx.TimeoutException:
                    logger.debug(
                        "[email/httpx] Timeout on homepage %s (limit=%.1fs)",
                        base_url, EMAIL_TIMEOUT,
                    )
                    return None
                except Exception as e:
                    logger.debug("[email/httpx] Homepage error for %s: %s", base_url, e)
                    return None

            # ── Parallel sub-page scan ────────────────────────────────────────
            email = await _scan_subpages_parallel(client, base_url, sub_paths)
            return email

    except Exception as e:
        logger.debug("[email/httpx] Session-level error for %s: %s", base_url, e)

    return None


async def _scan_subpages_parallel(
    client: httpx.AsyncClient,
    base_url: str,
    paths: list[str],
) -> str | None:
    """
    Fetch all sub-pages concurrently and return the first email found.
    Replaces sequential scanning — all pages fire at once instead of one-by-one.
    """
    async def _fetch_one(path: str) -> str | None:
        url = urljoin(base_url, path)
        try:
            resp = await client.get(url)
            size_kb = len(resp.content) / 1024
            logger.debug(
                "[email/httpx] GET %s → %d (%.1f KB)", url, resp.status_code, size_kb
            )
            if len(resp.content) > 5 * 1024 * 1024:
                logger.warning("[email/httpx] Response too large (%.1f KB) — skipping %s", size_kb, url)
                return None
            if resp.status_code < 400:
                return _find_email_in_html(resp.text, source=path)
        except Exception as e:
            logger.debug("[email/httpx] Error on %s: %s", url, e)
        return None

    results = await asyncio.gather(*[_fetch_one(p) for p in paths], return_exceptions=True)

    for result in results:
        if isinstance(result, str):
            return result
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Playwright fallback (JS-heavy sites)
# ─────────────────────────────────────────────────────────────────────────────

async def _extract_via_playwright(page: Page, base_url: str) -> str | None:
    """Use the Playwright page to scan the website for emails."""
    logger.debug("[email/playwright] Navigating to %s…", base_url)
    try:
        await page.goto(base_url, wait_until="load", timeout=int(EMAIL_TIMEOUT * 1000))
        # Scroll to bottom to trigger lazy-loaded footers where emails often live
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.0)  # Short wait for any lazy-loading
        html = await page.content()
        logger.debug("[email/playwright] Homepage loaded (%d chars)", len(html))

        email = _find_email_in_html(html, source="homepage (playwright)")
        if email:
            return email

        # Directly navigate to contact/about pages in Playwright
        # Use first 4 paths from EMAIL_COMMON_PATHS for more thorough search
        playwright_paths = EMAIL_COMMON_PATHS[:4]
        for path in playwright_paths:
            sub_url = urljoin(base_url, path)
            try:
                resp = await page.goto(
                    sub_url, wait_until="load", timeout=int(EMAIL_TIMEOUT * 1000)
                )
                if resp and resp.status < 400:
                    # Scroll for sub-pages too
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(0.5)
                    html = await page.content()
                    logger.debug(
                        "[email/playwright] %s loaded (%d chars)", path, len(html)
                    )
                    email = _find_email_in_html(html, source=f"{path} (playwright)")
                    if email:
                        return email
                else:
                    logger.debug("[email/playwright] %s → HTTP %s", path, resp.status if resp else "?")
            except Exception as e:
                logger.debug("[email/playwright] Navigate to %s error: %s", sub_url, e)

    except Exception as e:
        logger.debug("[email/playwright] Navigation failed: %s", e)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# HTML scanning
# ─────────────────────────────────────────────────────────────────────────────

def _find_email_in_html(html: str, *, source: str = "") -> str | None:
    """
    Scan HTML for email addresses, preferring mailto: links.
    Logs candidate counts and the accepted email.
    """
    src_tag = f" [{source}]" if source else ""

    # 1. mailto: links (most reliable — deliberate disclosure)
    mailto_hits = _MAILTO_RE.findall(html)
    logger.debug("[email] %s%s: %d mailto: candidates", "HTML scan", src_tag, len(mailto_hits))
    for raw in mailto_hits:
        email = validate_email(raw)
        if email:
            logger.debug("[email] ✓ Accepted from mailto:%s%s → %s", src_tag, src_tag, email)
            return email

    # 2. Full text regex scan
    emails = find_emails_in_text(html)
    if emails:
        logger.debug("[email] ✓ Accepted from regex scan%s → %s", src_tag, emails[0])
        return emails[0]

    logger.debug("[email] No valid email found%s", src_tag)
    return None
