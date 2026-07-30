"""
Social media link extraction from business websites.

Log coverage:
 - HTTP fetch method (httpx / Playwright) and status/size
 - Each platform: pattern matched, raw URL, cleaned URL
 - Platforms not found (so you know it was tried, not missed)
 - Final SocialMedia object summary
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from urllib.parse import urljoin

import httpx
from playwright.async_api import Page

from config.settings import EMAIL_TIMEOUT, SOCIAL_SCAN_PATHS
from models.business import SocialMedia
from scraper.utils import random_user_agent

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Platform detection patterns
# ─────────────────────────────────────────────────────────────────────────────

_PATTERNS: dict[str, re.Pattern] = {
    "facebook": re.compile(
        r'facebook\.com/(?!sharer|share|login|dialog|photo|video|events|permalink|groups/(?![\w.]+/))'
        r'([\w.%-]{3,})',
        re.IGNORECASE,
    ),
    "instagram": re.compile(r'instagram\.com/([\w.]{1,30})/?(?:["\'\s>]|$)', re.IGNORECASE),
    "twitter":   re.compile(r'(?:twitter|x)\.com/([\w]{1,15})(?:["\'\s/>]|$)', re.IGNORECASE),
    "linkedin":  re.compile(r'linkedin\.com/(?:company|in|school)/([\w%-]{2,100})', re.IGNORECASE),
    # YouTube fix: require "/" between the path-type prefix and the actual handle.
    # Without this, regex alternation backtracks from "channel" to "c", matching
    # "c" + "hannel" and producing handles like "hannel" instead of the real channel ID.
    # "@" handles (e.g. youtube.com/@name) use @ as the separator, no "/" needed.
    "youtube": re.compile(
        r'youtube\.com/(?:(?:channel|user|c)/|@)([\w%-]{2,100})',
        re.IGNORECASE,
    ),
    "tiktok":    re.compile(r'tiktok\.com/@?([\w.]{2,30})(?:["\'\s/>]|$)', re.IGNORECASE),
}

_SKIP_HANDLES: frozenset[str] = frozenset({
    # Generic navigation / auth
    "home", "login", "logout", "signup", "register", "help", "support",
    "about", "privacy", "terms", "legal", "press", "business", "ads",
    "sharer", "share", "dialog", "intent", "hashtag",
    # Facebook-specific generic paths that are NOT business profile pages
    "people",           # facebook.com/people/Name → generic people search
    "profile",          # facebook.com/profile (generic)
    "profile.php",      # facebook.com/profile.php?id=... (old-style profile URL)
    "groups",           # facebook.com/groups → groups browser
    "pages",            # facebook.com/pages → pages browser
    "watch",            # facebook.com/watch → video feed
    "marketplace",      # facebook.com/marketplace
    "gaming",           # facebook.com/gaming
    "messages",         # facebook.com/messages
    "notifications",    # facebook.com/notifications
    "search",           # facebook.com/search
    "settings",         # facebook.com/settings
    "friends",          # facebook.com/friends
    "events",           # facebook.com/events
    "stories",          # facebook.com/stories
    "saved",            # facebook.com/saved
    "find-friends",     # facebook.com/find-friends
    "policies",         # facebook.com/policies
    "pg",               # facebook.com/pg/... (old page format)
    "note",             # facebook.com/note
    "biz",              # facebook.com/biz
    # Instagram generic
    "explore",          # instagram.com/explore
    "accounts",         # instagram.com/accounts
    "reels",            # instagram.com/reels
    # YouTube generic
    "feed",             # youtube.com/feed
    "results",          # youtube.com/results
    "watch",            # youtube.com/watch (video URLs)
    "playlist",         # youtube.com/playlist
})

_PROFILE_ROOTS: dict[str, str] = {
    "facebook":  "https://www.facebook.com/",
    "instagram": "https://www.instagram.com/",
    "twitter":   "https://www.x.com/",
    "linkedin":  "https://www.linkedin.com/",
    "youtube":   "https://www.youtube.com/",
    "tiktok":    "https://www.tiktok.com/@",
}


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

async def extract_social_media(
    website_url: str,
    page: Page | None = None,
    *,
    prefetched_html: str | None = None,
) -> SocialMedia:
    """
    Scan the business website for social media profile links.

    Args:
        website_url:     The business website URL.
        page:            Playwright page for JS-heavy fallback (optional).
        prefetched_html: Homepage HTML already fetched by fetch_homepage_html().
                         When provided, skips the homepage HTTP request entirely
                         and fetches only sub-pages (in parallel).

    Results across all pages are merged so that a Facebook link on the /contact
    page isn't missed.
    Returns a SocialMedia model populated with whatever links were found.
    """
    if not website_url:
        logger.debug("[social] No website URL — skipping social extraction")
        return SocialMedia()

    start = time.monotonic()
    logger.debug("[social] Extracting from: %s", website_url)

    combined_html = ""

    if prefetched_html:
        # Homepage already fetched — use it and only fetch sub-pages
        combined_html += prefetched_html
        logger.debug("[social] Using prefetched homepage HTML (%d chars)", len(prefetched_html))
        sub_pages = await _fetch_subpages_parallel(website_url)
        for path, html in sub_pages:
            if html:
                combined_html += html
                logger.debug("[social/httpx] %s: %d chars", path, len(html))
    else:
        # ── httpx: homepage + sub-pages (sub-pages fetched in parallel) ──────
        homepage_html = await _fetch_html_httpx(website_url)
        if homepage_html:
            combined_html += homepage_html
            logger.debug("[social/httpx] Homepage: %d chars", len(homepage_html))
            sub_pages = await _fetch_subpages_parallel(website_url)
            for path, html in sub_pages:
                if html:
                    combined_html += html
                    logger.debug("[social/httpx] %s: %d chars", path, len(html))

    # ── Playwright fallback/supplement ───────────────────────────────────────
    # If httpx found nothing, OR it's missing key platforms (FB/Insta),
    # try Playwright to render JS-heavy content.
    if page is not None:
        if not combined_html:
            logger.debug("[social] httpx returned nothing — trying Playwright fallback…")
            pw_html = await _fetch_html_playwright(page, website_url)
            if pw_html:
                combined_html += pw_html
                logger.debug("[social/playwright] Homepage: %d chars", len(pw_html))
                for path in SOCIAL_SCAN_PATHS:
                    sub_url = urljoin(website_url, path)
                    sub_html = await _fetch_html_playwright(page, sub_url)
                    if sub_html:
                        combined_html += sub_html
                        logger.debug("[social/playwright] %s: %d chars", path, len(sub_html))

        else:
            partial = _parse_social_links(combined_html)
            missing = [p for p in ("facebook", "instagram") if not getattr(partial, p)]
            if missing:
                logger.debug(
                    "[social] httpx missing %s — trying Playwright supplement…", missing
                )
                pw_html = await _fetch_html_playwright(page, website_url)
                if pw_html:
                    combined_html += pw_html
                    # Also try contact/about if still missing
                    revised = _parse_social_links(combined_html)
                    still_missing = [p for p in ("facebook", "instagram") if not getattr(revised, p)]
                    if still_missing:
                         for path in SOCIAL_SCAN_PATHS:
                            sub_url = urljoin(website_url, path)
                            sub_html = await _fetch_html_playwright(page, sub_url)
                            if sub_html:
                                combined_html += sub_html
    
    if not combined_html:
        logger.debug("[social] Could not fetch HTML from %s — no social links", website_url)
        return SocialMedia()

    logger.debug("[social] Scanning %d total chars of HTML…", len(combined_html))
    result = _parse_social_links(combined_html)

    # Summary log
    found = {k: v for k, v in result.model_dump().items() if v}
    not_found = [k for k in _PATTERNS if k not in found]
    logger.debug(
        "[social] Done in %.1fs | found=%s | not_found=%s",
        time.monotonic() - start,
        list(found.keys()) or "none",
        not_found,
    )
    for platform, url in found.items():
        logger.debug("  ✓ %-12s = %s", platform, url)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Fetching
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_html_httpx(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": random_user_agent()},
            timeout=EMAIL_TIMEOUT,
            follow_redirects=True,
            verify=False,
        ) as client:
            resp = await client.get(url)
            size_kb = len(resp.content) / 1024
            logger.debug(
                "[social/httpx] GET %s → %d (%.1f KB)", url, resp.status_code, size_kb
            )
            if resp.status_code < 400:
                return resp.text
            logger.debug(
                "[social/httpx] HTTP %d — not scanning this response", resp.status_code
            )
    except httpx.ConnectError as e:
        logger.debug("[social/httpx] Connection error for %s: %s", url, e)
    except httpx.TimeoutException:
        logger.debug("[social/httpx] Timeout for %s (limit=%.1fs)", url, EMAIL_TIMEOUT)
    except Exception as e:
        logger.debug("[social/httpx] Unexpected error for %s: %s", url, e)
    return None


async def _fetch_subpages_parallel(base_url: str) -> list[tuple[str, str | None]]:
    """
    Fetch all SOCIAL_SCAN_PATHS sub-pages concurrently via httpx.
    Returns a list of (path, html) tuples. html is None on error/timeout.
    Replaces sequential sub-page scanning — all pages fire at once.
    """
    async def _get(path: str) -> tuple[str, str | None]:
        url = urljoin(base_url, path)
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": random_user_agent()},
                timeout=EMAIL_TIMEOUT,
                follow_redirects=True,
                verify=False,
            ) as client:
                resp = await client.get(url)
                if resp.status_code < 400:
                    return path, resp.text
        except Exception:
            pass
        return path, None

    results = await asyncio.gather(*[_get(p) for p in SOCIAL_SCAN_PATHS], return_exceptions=True)
    return [(p, h) for r in results for p, h in [r if isinstance(r, tuple) else ("?", None)]]


async def _fetch_html_playwright(page: Page, url: str) -> str | None:
    try:
        await page.goto(url, wait_until="load", timeout=int(EMAIL_TIMEOUT * 1000))
        # Scroll to bottom to trigger lazy-loaded footers where social links often live
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.0)  # Short wait for any lazy-loading
        html = await page.content()
        logger.debug("[social/playwright] Loaded %s (%d chars)", url, len(html))
        return html
    except Exception as e:
        logger.debug("[social/playwright] Failed to load %s: %s", url, e)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Parsing
# ─────────────────────────────────────────────────────────────────────────────

def _parse_social_links(html: str) -> SocialMedia:
    found: dict[str, str] = {}

    for platform, pattern in _PATTERNS.items():
        matches = list(pattern.finditer(html))
        if not matches:
            logger.debug("  [social] ✗ %-12s — no pattern match in HTML", platform)
            continue

        # Evaluate matches in order, take the first valid one
        accepted = False
        for match in matches:
            handle = match.group(1).strip("/").lower()
            if handle in _SKIP_HANDLES:
                logger.debug(
                    "  [social] %-12s — skipped handle %r (platform own page)",
                    platform, handle,
                )
                continue
            raw_url = match.group(0).strip().rstrip('"\' ')
            clean_url = _normalise_url(platform, raw_url, handle)
            logger.debug(
                "  [social] ✓ %-12s — handle=%r url=%s", platform, handle, clean_url
            )
            found[platform] = clean_url
            accepted = True
            break

        if not accepted:
            logger.debug(
                "  [social] ✗ %-12s — %d match(es) but all handles were skipped",
                platform, len(matches),
            )

    return SocialMedia(**found)


def _normalise_url(platform: str, raw_match: str, handle: str) -> str:
    """
    Build a canonical, fully-qualified profile URL.

    raw_match is match.group(0) — the full regex match fragment, which may be:
      • A complete URL:        "https://www.linkedin.com/company/acme"
      • Domain-relative:      "linkedin.com/company/acme"
      • Protocol-relative:    "//linkedin.com/company/acme"
    handle is match.group(1) — only the trailing handle/ID part.
    """
    # Sanitize trailing HTML artifacts from the raw match
    for stop_char in ('"', "'", ">", " ", "\n", "\r", "\t"):
        raw_match = raw_match.split(stop_char)[0]
    raw_match = raw_match.strip().rstrip("/")

    # Case 1: already a full absolute URL
    if raw_match.startswith(("http://", "https://")):
        return _ensure_tiktok_at(platform, raw_match)

    # Case 2: protocol-relative ("//linkedin.com/company/acme")
    if raw_match.startswith("//"):
        return _ensure_tiktok_at(platform, "https:" + raw_match)

    # Case 3: domain-relative ("linkedin.com/company/acme", "youtube.com/channel/UC...")
    # The raw match includes the platform domain + the path type + the handle,
    # so we can reconstruct a clean URL by prepending "https://www.".
    _PLATFORM_DOMAINS = {
        "facebook": "facebook.com",
        "instagram": "instagram.com",
        "twitter": "x.com",
        "linkedin": "linkedin.com",
        "youtube": "youtube.com",
        "tiktok": "tiktok.com",
    }
    expected_domain = _PLATFORM_DOMAINS.get(platform, "")
    if expected_domain and expected_domain in raw_match.lower():
        # Strip any leading "www." before prepending our canonical "https://www."
        clean = re.sub(r"^(?:https?://)?(?:www\.)?", "", raw_match, flags=re.IGNORECASE)
        return _ensure_tiktok_at(platform, f"https://www.{clean}")

    # Case 4: bare handle (fallback, should rarely be hit with our patterns)
    root = _PROFILE_ROOTS.get(platform, f"https://www.{platform}.com/")
    result = f"{root}{handle}"
    return _ensure_tiktok_at(platform, result)


def _ensure_tiktok_at(platform: str, url: str) -> str:
    """
    TikTok profile URLs must have '@' before the handle.
    Some websites link to 'tiktok.com/brandname' (no @) — normalise to 'tiktok.com/@brandname'.
    This runs as a final post-processing step on all normalised TikTok URLs.
    """
    if platform != "tiktok":
        return url
    # Already has @ → fine
    if "/@" in url:
        return url
    # Insert @ after 'tiktok.com/'
    return re.sub(
        r'(tiktok\.com/)(?!@)([\w.%-]+)',
        r'\1@\2',
        url,
        flags=re.IGNORECASE,
    )
