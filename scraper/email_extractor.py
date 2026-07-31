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
from urllib.parse import urljoin, urlparse

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
_ANCHOR_HREF_RE = re.compile(
    r'<a\s+(?:[^>]*?\s+)?href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

_HTTPX_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def _extract_contact_links_from_html(html: str, base_url: str) -> list[str]:
    """Extract candidate sub-page relative paths from homepage anchor links (<a href="...">)."""
    if not html:
        return []
    keywords = ("contact", "about", "team", "reach", "connect", "privacy", "impressum", "agent")
    candidate_paths: list[str] = []
    seen: set[str] = set()

    try:
        base_domain = urlparse(base_url).netloc.lower().lstrip("www.")
    except Exception:
        return []

    for href in _ANCHOR_HREF_RE.findall(html):
        href_clean = href.strip()
        if not href_clean or href_clean.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        try:
            full_url = urljoin(base_url, href_clean)
            parsed = urlparse(full_url)
            link_domain = parsed.netloc.lower().lstrip("www.")
            if link_domain and link_domain != base_domain:
                continue
            path = parsed.path
            if not path or path == "/" or path in seen:
                continue
            path_lower = path.lower()
            if any(kw in path_lower for kw in keywords):
                seen.add(path)
                candidate_paths.append(path)
        except Exception:
            continue

    return candidate_paths


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
        email = await _extract_via_playwright(page, website_url, prefetched_html=prefetched_html)
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
    Scan homepage + dynamic anchor links + common sub-pages using httpx.
    """
    homepage_html = prefetched_html
    pages_already_tried = 0

    # ── Step 1: try prefetched homepage HTML first ────────────────────────────
    if homepage_html:
        email = _find_email_in_html(homepage_html, source="homepage (prefetched)")
        if email:
            return email
        logger.debug("[email/httpx] Prefetched HTML had no email — harvesting sub-page links…")
        pages_already_tried = 1

    # ── Step 2: Assemble sub-page targets (dynamic anchor links + common paths) ──
    dynamic_paths = _extract_contact_links_from_html(homepage_html or "", base_url)
    combined_paths: list[str] = []
    seen: set[str] = set()

    for p in dynamic_paths + EMAIL_COMMON_PATHS:
        if p not in seen:
            seen.add(p)
            combined_paths.append(p)

    remaining_slots = MAX_EMAIL_PAGES - pages_already_tried
    if remaining_slots <= 0:
        logger.debug("[email/httpx] No sub-page slots remaining after homepage")
        return None

    sub_paths = combined_paths[:remaining_slots]

    try:
        async with httpx.AsyncClient(
            headers={**_HTTPX_HEADERS, "User-Agent": random_user_agent()},
            timeout=EMAIL_TIMEOUT,
            follow_redirects=True,
            verify=False,
        ) as client:

            if not homepage_html:
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
                        homepage_html = resp.text
                        email = _find_email_in_html(homepage_html, source="homepage")
                        if email:
                            return email
                        # Harvest anchor links from freshly fetched homepage HTML
                        dynamic_paths = _extract_contact_links_from_html(homepage_html, base_url)
                        combined_paths = []
                        seen = set()
                        for p in dynamic_paths + EMAIL_COMMON_PATHS:
                            if p not in seen:
                                seen.add(p)
                                combined_paths.append(p)
                        sub_paths = combined_paths[:remaining_slots]
                except Exception as e:
                    logger.debug("[email/httpx] Homepage fetch error for %s: %s", base_url, e)

            # ── Parallel sub-page scan ────────────────────────────────────────
            if sub_paths:
                logger.debug(
                    "[email/httpx] Scanning %d sub-pages in parallel for %s: %s",
                    len(sub_paths), base_url, sub_paths,
                )
                email = await _scan_subpages_parallel(client, base_url, sub_paths)
                if email:
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

def _is_bot_challenge_html(html: str) -> bool:
    """Return True if HTML response is a bot-protection or captcha challenge stub."""
    if not html or len(html) < 200:
        return True
    if len(html) < 20000:
        lower = html.lower()
        if any(term in lower for term in ("just a moment...", "enable javascript", "cloudflare", "attention required!", "ddos-guard", "verify you are human")):
            return True
    return False


async def _extract_via_playwright(
    page: Page,
    base_url: str,
    prefetched_html: str | None = None,
) -> str | None:
    """Use Playwright page to scan JS-rendered website for emails with domcontentloaded wait strategy."""
    logger.debug("[email/playwright] Navigating to %s…", base_url)
    timeout_ms = int(EMAIL_TIMEOUT * 1000)

    try:
        # domcontentloaded is much faster and reliable for JS-heavy sites than 'load'
        try:
            await page.goto(base_url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception:
            # Fallback to commit if domcontentloaded times out
            await page.goto(base_url, wait_until="commit", timeout=timeout_ms)

        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.5)  # Wait for JS hydration & footer rendering

        # 1. Check live DOM mailto hrefs (catches JS-injected mailto links)
        try:
            mailto_hrefs = await page.eval_on_selector_all(
                'a[href*="mailto:"]',
                'els => els.map(e => e.href)'
            )
            for raw_href in mailto_hrefs:
                m = _MAILTO_RE.search(raw_href)
                if m:
                    v = validate_email(m.group(1))
                    if v:
                        logger.debug("[email/playwright] Found via live DOM mailto href: %s", v)
                        return v
        except Exception as e:
            logger.debug("[email/playwright] DOM mailto query error: %s", e)

        # 2. Check full HTML content
        html = await page.content()
        logger.debug("[email/playwright] Homepage loaded (%d chars)", len(html))

        email = _find_email_in_html(html, source="homepage (playwright)")
        if email:
            return email

        # 3. Check rendered inner text of the page body
        try:
            body_text = await page.inner_text("body")
            email = _find_email_in_html(body_text, source="homepage inner_text (playwright)")
            if email:
                return email
        except Exception:
            pass

        # Harvest dynamic links inside Playwright
        dynamic_paths = _extract_contact_links_from_html(html, base_url)
        combined_paths: list[str] = []
        seen: set[str] = set()
        for p in dynamic_paths + EMAIL_COMMON_PATHS:
            if p not in seen:
                seen.add(p)
                combined_paths.append(p)

        playwright_paths = combined_paths[:4]
        for path in playwright_paths:
            sub_url = urljoin(base_url, path)
            try:
                resp = await page.goto(
                    sub_url, wait_until="domcontentloaded", timeout=timeout_ms
                )
                if resp and resp.status < 400:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1.0)
                    sub_html = await page.content()
                    logger.debug(
                        "[email/playwright] %s loaded (%d chars)", path, len(sub_html)
                    )
                    email = _find_email_in_html(sub_html, source=f"{path} (playwright)")
                    if email:
                        return email

                    # Also check inner_text of sub-page
                    try:
                        sub_text = await page.inner_text("body")
                        email = _find_email_in_html(sub_text, source=f"{path} inner_text (playwright)")
                        if email:
                            return email
                    except Exception:
                        pass
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
    Scan HTML for email addresses, preferring mailto: links and Cloudflare de-obfuscation.
    """
    if not html:
        return None

    src_tag = f" [{source}]" if source else ""

    # 1. mailto: links (most reliable — deliberate disclosure)
    mailto_hits = _MAILTO_RE.findall(html)
    logger.debug("[email] %s%s: %d mailto: candidates", "HTML scan", src_tag, len(mailto_hits))
    for raw in mailto_hits:
        email = validate_email(raw)
        if email:
            logger.debug("[email] ✓ Accepted from mailto:%s → %s", src_tag, email)
            return email

    # 2. Full text scan (includes Cloudflare decoding, HTML unescaping & obfuscation replacement)
    emails = find_emails_in_text(html)
    if emails:
        logger.debug("[email] ✓ Accepted from text scan%s → %s", src_tag, emails[0])
        return emails[0]

    logger.debug("[email] No valid email found%s", src_tag)
    return None

