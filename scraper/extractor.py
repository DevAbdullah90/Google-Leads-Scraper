"""
Core per-business data extraction from Google Maps detail pages.

Log coverage (every field, every step):
 ─ Navigation: URL, wait state, timing, final URL after redirect
 ─ Field extraction: which selector matched, raw value, validated value
 ─ Coordinates / place_id: parsed from URL with regex
 ─ Hours: aria-label text, expanded table rows
 ─ Reviews: each review's author/rating/text/date
 ─ Images: count and first URL
 ─ Website extraction trigger: email + social
 ─ Business summary banner on completion

Reading a DEBUG log for one business should answer every "why is field X empty?" question.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Callable

from playwright.async_api import Page

from config.selectors import (
    ABOUT_TAB_SELECTORS,
    ADDRESS_SELECTORS,
    ALL_PHOTOS_SELECTORS,
    ATTRIBUTE_ITEM_SELECTORS,
    BUSINESS_NAME_SELECTORS,
    CATEGORY_SELECTORS,
    DESCRIPTION_SELECTORS,
    HOURS_BUTTON_SELECTORS,
    HOURS_EXPANDED_SELECTORS,
    HOURS_STATUS_SELECTORS,
    MAIN_IMAGE_SELECTORS,
    PHONE_SELECTORS,
    PRICE_SELECTORS,
    RATING_VALUE_SELECTORS,
    REVIEW_AUTHOR_SELECTORS,
    REVIEW_COUNT_SELECTORS,
    REVIEW_DATE_SELECTORS,
    REVIEW_ITEM_SELECTORS,
    REVIEW_RATING_SELECTORS,
    REVIEW_TEXT_SELECTORS,
    REVIEWS_TAB_SELECTORS,
    WEBSITE_SELECTORS,
)
from config.settings import MAX_IMAGES, MAX_REVIEWS_SAMPLE, SCRAPER_VERSION
from models.business import (
    Address,
    Attributes,
    Business,
    BusinessInfo,
    Contact,
    Coordinates,
    Hours,
    HoursByDay,
    Images,
    Metadata,
    Ratings,
    Review,
    SocialMedia,
)
from scraper.email_extractor import extract_email, fetch_homepage_html
from scraper.parser import (
    all_elements,
    first_attr,
    first_element,
    first_text,
    get_attr,
    get_text,
)
from scraper.social_extractor import extract_social_media
from scraper.utils import action_delay, log_field, log_section, log_subsection, timed_op
from scraper.validator import (
    parse_rating_text,
    parse_review_count,
    validate_email,
    validate_phone,
    validate_url,
    validate_coordinates,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# URL utilities
# ─────────────────────────────────────────────────────────────────────────────

def _coords_from_url(url: str) -> tuple[float | None, float | None]:
    # Format 1: @lat,lng,zoom  (present after Google Maps redirects to the clean URL)
    match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if match:
        try:
            lat, lng = float(match.group(1)), float(match.group(2))
            logger.debug("  Parsed coords from URL (@format): (%.6f, %.6f)", lat, lng)
            return validate_coordinates(lat, lng)
        except ValueError as e:
            logger.debug("  Coord @format parse error: %s", e)

    # Format 2: !3d{lat}!4d{lng}  (present in the data= parameter of place URLs)
    # e.g. /maps/place/Name/data=!4m7!3m6!1s...!8m2!3d25.2139289!4d55.2823472
    match = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", url)
    if match:
        try:
            lat, lng = float(match.group(1)), float(match.group(2))
            logger.debug("  Parsed coords from URL (!3d/!4d format): (%.6f, %.6f)", lat, lng)
            return validate_coordinates(lat, lng)
        except ValueError as e:
            logger.debug("  Coord !3d/!4d format parse error: %s", e)

    logger.debug("  No coords found in URL (tried @lat,lng and !3d/!4d formats)")
    return None, None


def _place_id_from_url(url: str) -> str | None:
    # Hex-encoded place ID (most common in current URLs)
    match = re.search(r"(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)", url)
    if match:
        pid = match.group(1)
        logger.debug("  place_id extracted (hex): %s", pid)
        return pid
    # Legacy ChIJ format in query param
    match = re.search(r"place_id=(ChIJ[A-Za-z0-9_-]+)", url)
    if match:
        pid = match.group(1)
        logger.debug("  place_id extracted (ChIJ): %s", pid)
        return pid
    logger.debug("  place_id not found in URL")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Main extraction function
# ─────────────────────────────────────────────────────────────────────────────

async def extract_business(
    page: Page,
    url: str,
    query: str = "",
    *,
    on_business_scraped: Callable | None = None,
) -> Business | None:
    """
    Navigate to `url` and extract all available business data.

    Returns a Business object, or None if the page couldn't be parsed.
    Never raises — all errors caught and logged.
    """
    extract_start = time.monotonic()

    logger.debug("── Navigating to business URL ──────────────────────────────────")
    logger.debug("  URL: %s", url)

    # ── Navigation ────────────────────────────────────────────────────────────
    try:
        async with timed_op(logger, "page.goto(domcontentloaded)"):
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except Exception as e:
        logger.error("Navigation FAILED for: %s", url)
        logger.error("  Error: %s", e)
        return None

    final_url = page.url
    if final_url != url:
        logger.debug("  Redirected → %s", final_url)

    # ── Wait for name element (page-load proof) ────────────────────────────────
    logger.debug("  Waiting for business name element (%d selectors)…", len(BUSINESS_NAME_SELECTORS))
    loaded = False
    for selector in BUSINESS_NAME_SELECTORS[:3]:
        try:
            await page.wait_for_selector(selector, timeout=10_000)
            logger.debug("  Page loaded — name selector ready: %r", selector)
            loaded = True
            break
        except Exception:
            continue

    if not loaded:
        logger.warning(
            "Business name element NOT FOUND after page load at: %s", url
        )
        logger.warning(
            "  Tried: %s", BUSINESS_NAME_SELECTORS[:3]
        )
        logger.warning(
            "  Possible causes: Google layout changed, page error, or wrong URL."
        )
        return None

    await action_delay()

    # ── Extract every field ────────────────────────────────────────────────────
    log_subsection(logger, "FIELD EXTRACTION", char="─")

    name = await _extract_name(page)
    log_field(logger, "name", name)
    if not name:
        logger.warning("business_name is empty — skipping this URL: %s", url)
        return None

    lat, lng = _coords_from_url(final_url)
    if lat is None:
        # final_url may not yet have @lat,lng if redirect didn't happen;
        # the original URL always contains !3d/!4d in its data= parameter
        lat, lng = _coords_from_url(url)
        if lat is not None:
            logger.debug("  coords resolved from original URL (final_url had none)")
    log_field(logger, "coordinates", f"({lat}, {lng})" if lat else None)

    place_id = _place_id_from_url(final_url)
    log_field(logger, "place_id", place_id or None)

    category, all_categories = await _extract_categories(page)
    log_field(logger, "category", category)
    if all_categories:
        logger.debug("  ℹ all_categories = %s", all_categories)

    avg_rating, total_reviews = await _extract_rating(page)
    log_field(logger, "rating", f"{avg_rating} ({total_reviews} reviews)" if avg_rating else None)

    address_obj = await _extract_address(page)
    log_field(logger, "address", address_obj.full_address)
    if address_obj.full_address:
        logger.debug(
            "  ℹ address components: city=%r, country=%r, postal=%r",
            address_obj.city, address_obj.country, address_obj.postal_code,
        )

    phone = await _extract_phone(page)
    log_field(logger, "phone", phone)

    website = await _extract_website(page)
    log_field(logger, "website", website)

    hours = await _extract_hours(page)
    log_field(logger, "hours.status", hours.current_status)
    log_field(logger, "hours.is_open", hours.is_open_now)
    hours_data = {k: v for k, v in hours.hours_by_day.model_dump().items() if v}
    if hours_data:
        logger.debug("  ℹ hours by day: %s", hours_data)
    else:
        logger.debug("  ℹ hours by day: (not extracted)")

    # price_level: extracted while still on Overview tab (before any tab-switch)
    # so the category/price subheader row is in its default visible state.
    price_level = await _extract_price(page)
    log_field(logger, "price_level", price_level)

    # description: internally clicks the About tab to reveal the description panel.
    # Must run after price (which needs Overview tab state) but before attributes
    # (which also clicks About — the second click is harmless).
    description = await _extract_description(page)
    log_field(logger, "description",
              (description[:60] + "…") if description and len(description) > 60 else description)

    images = await _extract_images(page)
    log_field(logger, "images",
              f"{len(images.all_image_urls)} URLs" if images.all_image_urls else None)

    # Extract attributes — this internally clicks the "About" tab.
    attributes = await _extract_attributes(page)
    amenity_count = len(attributes.amenities)
    log_field(logger, "attributes", f"{amenity_count} amenity tags" if amenity_count else None)

    # Reviews tab click changes the visible panel — must be last among Google Maps extractions.
    # (About tab click inside _extract_attributes may have moved us away from Overview,
    # but _extract_reviews will click the Reviews tab regardless of current tab state.)
    reviews, panel_review_count = await _extract_reviews(page)
    log_field(logger, "reviews_sample", f"{len(reviews)} reviews" if reviews else None)

    # Use the Reviews-panel count as fallback when the overview count didn't render
    # (Google's limited-view mode omits the count from the main listing page).
    if total_reviews is None and panel_review_count is not None:
        total_reviews = panel_review_count
        logger.debug("  [review_count] using Reviews-panel count as fallback: %d", total_reviews)

    # ── Website-based extraction ───────────────────────────────────────────────
    email: str | None = None
    social: SocialMedia = SocialMedia()

    if website:
        log_subsection(logger, "WEBSITE EXTRACTION", char="─")
        logger.debug("  Website: %s", website)

        # Fetch the homepage HTML once — shared by both email and social extractors.
        # This avoids two separate HTTP requests to the same URL.
        homepage_html = await fetch_homepage_html(website)
        if homepage_html:
            logger.debug("  Homepage prefetched (%d chars) — sharing with email + social", len(homepage_html))
        else:
            logger.debug("  Homepage prefetch failed — extractors will fetch independently")

        # Email
        logger.debug("  ▶ Extracting email from website…")
        try:
            email = await extract_email(website, page, prefetched_html=homepage_html)
            log_field(logger, "email", email)
        except Exception as e:
            logger.warning("  Email extraction raised unexpected error: %s", e)

        # Social media
        logger.debug("  ▶ Extracting social media links from website…")
        try:
            social = await extract_social_media(website, page, prefetched_html=homepage_html)
            social_found = {k: v for k, v in social.model_dump().items() if v}
            if social_found:
                logger.debug("  Social links found: %s", list(social_found.keys()))
            else:
                logger.debug("  No social media links found.")
        except Exception as e:
            logger.warning("  Social extraction raised unexpected error: %s", e)
    else:
        logger.debug("  No website URL — skipping email + social extraction.")

    # ── Assemble Business object ───────────────────────────────────────────────
    business = Business(
        business_name=name,
        place_id=place_id or "",
        google_maps_url=url,
        address=address_obj,
        coordinates=Coordinates(latitude=lat, longitude=lng),
        contact=Contact(
            phone=phone,
            website=website,
            email=validate_email(email),
        ),
        social_media=social,
        business_info=BusinessInfo(
            category=category,
            all_categories=all_categories,
            description=description,
            price_level=price_level,
        ),
        ratings=Ratings(
            average_rating=avg_rating,
            total_reviews=total_reviews,
        ),
        hours=hours,
        attributes=attributes,
        images=images,
        reviews_sample=reviews,
        metadata=Metadata(
            scraped_at=datetime.now(timezone.utc).isoformat(),
            scraper_version=SCRAPER_VERSION,
            query=query,
        ),
    )

    elapsed = time.monotonic() - extract_start
    _log_business_summary(business, elapsed)

    if on_business_scraped:
        try:
            result = on_business_scraped(business.to_dict())
            if hasattr(result, "__await__"):
                await result
        except Exception as e:
            logger.debug("on_business_scraped callback error: %s", e)

    return business


# ─────────────────────────────────────────────────────────────────────────────
# Field extractors (each logs its own selector-level detail)
# ─────────────────────────────────────────────────────────────────────────────

async def _extract_name(page: Page) -> str | None:
    logger.debug("  [name] trying %d selectors…", len(BUSINESS_NAME_SELECTORS))
    return await first_text(page, BUSINESS_NAME_SELECTORS)


async def _extract_categories(page: Page) -> tuple[str | None, list[str]]:
    logger.debug("  [category] trying %d selectors…", len(CATEGORY_SELECTORS))
    elements = await all_elements(page, CATEGORY_SELECTORS)
    cats: list[str] = []
    for el in elements:
        text = await get_text(el)
        if text:
            cats.append(text)
    if not cats:
        logger.debug("  [category] no categories found")
    return (cats[0] if cats else None), cats


async def _extract_rating(page: Page) -> tuple[float | None, int | None]:
    logger.debug("  [rating] trying %d selectors…", len(RATING_VALUE_SELECTORS))
    rating_text = await first_text(page, RATING_VALUE_SELECTORS)
    if not rating_text:
        # Some layouts render the rating only in aria-label (e.g. "4.7 stars")
        rating_text = await first_attr(page, RATING_VALUE_SELECTORS, "aria-label")
        if rating_text:
            logger.debug("  [rating] fell back to aria-label: %r", rating_text)
    avg = parse_rating_text(rating_text)
    if rating_text and avg is None:
        logger.debug("  [rating] raw text %r could not be parsed as a rating", rating_text)

    # Step 1: wait up to 3 s for .lyplG to render (Google lazy-loads the count).
    try:
        await page.wait_for_selector(".lyplG:not(:empty)", timeout=3000)
        logger.debug("  [review_count] .lyplG populated")
    except Exception:
        logger.debug("  [review_count] .lyplG still empty after 3 s (limited view or slow load)")

    # Step 2: try CSS selectors for visible count text only — no aria-labels.
    # Visible text (e.g. "(268)") is the canonical displayed count.
    # aria-labels carry Google's ALL-LANGUAGES total which differs from the UI.
    logger.debug("  [review_count] trying %d selectors…", len(REVIEW_COUNT_SELECTORS))
    count_text = await first_text(page, REVIEW_COUNT_SELECTORS)
    total = parse_review_count(count_text) if count_text else None
    if count_text and total is None:
        logger.debug("  [review_count] raw text %r could not be parsed as integer", count_text)

    # Step 3: JS visible-text scan — reads displayed count from the DOM structure
    # without touching aria-labels.
    if total is None:
        try:
            visible_count: str | None = await page.evaluate("""
                () => {
                    // .lyplG is the current container for the review count
                    const ly = document.querySelector('.lyplG');
                    if (ly && ly.innerText.trim()) {
                        const t = ly.innerText.trim();
                        const m = t.match(/\\(?([\\d,]+)\\)?/);
                        if (m) return m[1];
                    }

                    // Walk siblings of the stars element for a plain integer
                    const starsEl = document.querySelector(
                        'span[role="img"][aria-label*="star"]'
                    );
                    if (starsEl) {
                        let sib = starsEl.nextElementSibling;
                        for (let i = 0; i < 5 && sib; i++) {
                            const t = (sib.innerText || '').trim();
                            const m = t.match(/^\\(?([\\d,]+)\\)?$/);
                            if (m && !t.includes('.')) return m[1];
                            sib = sib.nextElementSibling;
                        }
                    }

                    // Scan first 500 chars of main panel for "(N)" pattern
                    const main = document.querySelector('[role="main"]');
                    if (main) {
                        const chunk = (main.innerText || '').substring(0, 500);
                        const m = chunk.match(/\\(([\\d,]+)\\)/);
                        if (m) return m[1];
                    }

                    return null;
                }
            """)
            if visible_count:
                clean = visible_count.replace(",", "")
                if clean.isdigit():
                    total = int(clean)
                    logger.debug("  [review_count] JS visible text: %r → %d", visible_count, total)
        except Exception as e:
            logger.debug("  [review_count] JS visible scan error: %s", e)

    return avg, total


async def _extract_address(page: Page) -> Address:
    logger.debug("  [address] trying %d selectors…", len(ADDRESS_SELECTORS))
    full = await first_text(page, ADDRESS_SELECTORS)
    if not full:
        full = await first_attr(page, ADDRESS_SELECTORS, "aria-label")
        if full and full.lower().startswith("address:"):
            full = full[8:].strip()
            logger.debug("  [address] extracted from aria-label")
    if not full:
        logger.debug("  [address] not found via any method")
        return Address()
    return _parse_address_components(full)


def _parse_address_components(full: str) -> Address:
    """
    Parse address components from a Google Maps full address string.

    Dubai/UAE addresses typically use " - " as the separator:
      "Gate Village, Building 3 - DIFC - Dubai - United Arab Emirates"
      → street="Gate Village, Building 3"  city="Dubai"  country="United Arab Emirates"

    International addresses typically use ", " as the separator:
      "123 Main St, New York, NY 10001, United States"
      → street="123 Main St"  city="New York"  country="United States"
    """

    # Strategy A: " - " separated (UAE/Middle East style)
    dash_parts = [p.strip() for p in full.split(" - ") if p.strip()]
    if len(dash_parts) >= 3:
        # Pick the first part that looks like a real venue/street name.
        # Skip parts that are clearly not addresses:
        #   - "Floor N" / "Level N" — floor indicators only
        #   - "Valet parking available at ..." — operational notes
        #   - "No. N ..." alone — building numbers without a name (keep if name follows)
        street = dash_parts[0]
        for part in dash_parts[:-2]:   # don't pick city or country
            lower = part.lower()
            if re.match(r"^floor\s+\d", lower) or re.match(r"^level\s+\d", lower):
                continue   # skip pure floor indicators
            if lower.startswith("valet parking") or lower.startswith("parking available"):
                continue   # skip parking operational notes
            street = part
            break

        city    = dash_parts[-2]
        country = dash_parts[-1]
        postal_code: str | None = None
        for part in dash_parts:
            m = re.search(r"\b\d{4,10}\b", part)
            if m:
                postal_code = m.group(0)
                break
        logger.debug(
            "  [address] dash-split (%d parts): street=%r city=%r postal=%r country=%r",
            len(dash_parts), street, city, postal_code, country,
        )
        return Address(
            full_address=full,
            street=street,
            city=city or None,
            postal_code=postal_code,
            country=country,
        )

    # Strategy B: ", " separated (international / Western style)
    parts = [p.strip() for p in full.split(",") if p.strip()]
    if not parts:
        return Address(full_address=full)

    postal_code = None
    postal_idx: int | None = None
    for i, part in enumerate(parts):
        m = re.search(r"\b\d{4,10}\b", part)
        if m:
            postal_code = m.group(0)
            postal_idx = i
            break

    street  = parts[0]
    country = parts[-1] if len(parts) > 1 else None
    city: str | None = None

    if postal_idx is not None:
        # City is the part BEFORE the postal code component
        if postal_idx >= 2:
            city = parts[postal_idx - 1]
        elif postal_idx == 1 and len(parts) >= 3:
            city = re.sub(r"\b\d{4,10}\b", "", parts[postal_idx]).strip()
            if not city and postal_idx + 1 < len(parts):
                city = parts[postal_idx + 1]
    elif len(parts) >= 3:
        city = parts[-2]

    logger.debug(
        "  [address] comma-split (%d parts): street=%r city=%r postal=%r country=%r",
        len(parts), street, city, postal_code, country,
    )
    return Address(
        full_address=full,
        street=street,
        city=city or None,
        postal_code=postal_code,
        country=country,
    )


async def _extract_phone(page: Page) -> str | None:
    logger.debug("  [phone] trying %d selectors…", len(PHONE_SELECTORS))
    text = await first_text(page, PHONE_SELECTORS)
    if not text:
        raw = await first_attr(page, PHONE_SELECTORS, "aria-label")
        if raw and raw.lower().startswith("phone:"):
            text = raw[6:].strip()
            logger.debug("  [phone] extracted from aria-label: %r", text)
    result = validate_phone(text)
    if text and result is None:
        logger.debug("  [phone] raw %r rejected by validator", text)
    return result


async def _extract_website(page: Page) -> str | None:
    logger.debug("  [website] trying %d selectors…", len(WEBSITE_SELECTORS))
    href = await first_attr(page, WEBSITE_SELECTORS, "href")
    if href:
        # Google Maps wraps outbound links via /url?q=...
        if "/url?q=" in href:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
            decoded = qs.get("q", [None])[0]
            if decoded:
                logger.debug("  [website] decoded Google redirect → %r", decoded)
                return validate_url(decoded, reject_social=True)
            return None
        return validate_url(href, reject_social=True)
    # Fallback: read the display text
    text = await first_text(page, WEBSITE_SELECTORS)
    return validate_url(text, reject_social=True)


async def _extract_hours(page: Page) -> Hours:
    logger.debug("  [hours] trying status selectors…")
    status_text = await first_text(page, HOURS_STATUS_SELECTORS)
    if status_text:
        # Strip regular AND non-breaking/zero-width spaces that Google Maps inserts
        # at the end of status strings (U+00A0, U+202F, U+200B zero-width, etc.).
        status_text = re.sub(r'[\u00a0\u202f\u2009\u2060\ufeff\u200b\u200c\u200d\s]+$', '', status_text.strip())

    is_open: bool | None = None
    if status_text:
        lower = status_text.lower()
        # IMPORTANT: check "closed" BEFORE "open", because "Closed · Opens 12 PM"
        # contains the word "opens" which would incorrectly trigger is_open=True.
        if lower.startswith("closed"):
            is_open = False
        elif lower.startswith("closes soon") or lower.startswith("closing soon"):
            is_open = True
        elif lower.startswith("open"):
            is_open = True
        logger.debug("  [hours] status text: %r → is_open=%s", status_text, is_open)

    hours_by_day = HoursByDay()
    logger.debug("  [hours] trying hours button selectors (%d)…", len(HOURS_BUTTON_SELECTORS))
    hours_btn = await first_element(page, HOURS_BUTTON_SELECTORS)

    if hours_btn:
        # ── Step 1: read the pre-click aria-label (may already have all 7 days) ──
        try:
            pre_aria = await get_attr(hours_btn, "aria-label") or ""
            if pre_aria:
                pre_parsed = _parse_hours_aria(pre_aria)
                pre_days = sum(1 for v in pre_parsed.model_dump().values() if v)
                if pre_days >= 5:
                    logger.debug("  [hours] pre-click aria-label has %d days — using it directly", pre_days)
                    hours_by_day = pre_parsed
        except Exception:
            pass

        # ── Step 2: click to expand and try again if pre-click didn't give all days ──
        if sum(1 for v in hours_by_day.model_dump().values() if v) < 5:
            try:
                pre_click_url = page.url
                await hours_btn.click()
                if page.url.split("#")[0].split("?")[0] != pre_click_url.split("#")[0].split("?")[0]:
                    logger.warning("  [hours] click triggered navigation — aborting hours extraction")
                    return Hours(is_open_now=is_open, current_status=status_text)
                # Wait for the hours panel to fully expand before reading.
                # Try each known expansion indicator; fall back to fixed wait.
                expanded_seen = False
                for indicator in HOURS_EXPANDED_SELECTORS:
                    try:
                        await page.wait_for_selector(indicator, timeout=1500)
                        expanded_seen = True
                        break
                    except Exception:
                        continue
                if not expanded_seen:
                    await page.wait_for_timeout(1200)

                # ── Step 3: DOM-agnostic JS extraction ──
                hours_js = await _extract_hours_via_js(page)
                if hours_js:
                    js_days = sum(1 for v in hours_js.model_dump().values() if v)
                    if js_days >= 2:
                        logger.debug("  [hours] JS extraction gave %d days", js_days)
                        hours_by_day = hours_js
                    else:
                        logger.debug("  [hours] JS extraction gave only %d days", js_days)

                # ── Step 4: post-click aria-label as fallback ──
                if sum(1 for v in hours_by_day.model_dump().values() if v) < 2:
                    try:
                        hours_btn2 = await first_element(page, HOURS_BUTTON_SELECTORS)
                        post_aria = await get_attr(hours_btn2 or hours_btn, "aria-label") or ""
                        if post_aria and post_aria != pre_aria:
                            post_parsed = _parse_hours_aria(post_aria)
                            post_days = sum(1 for v in post_parsed.model_dump().values() if v)
                            if post_days >= 2:
                                logger.debug("  [hours] post-click aria-label gave %d days", post_days)
                                hours_by_day = post_parsed
                    except Exception:
                        pass

            except Exception as e:
                logger.debug("  [hours] click/expand failed: %s", e)
    else:
        logger.debug("  [hours] no hours button found via any selector")

    # ── Sanity check: reject wrong data ──
    if is_open and hours_by_day:
        day_values = [v for v in hours_by_day.model_dump().values() if v is not None]
        closed_days = sum(1 for v in day_values if v.lower().strip() == "closed")
        if closed_days >= 5:
            logger.debug(
                "  [hours] discarding — %d days say Closed but status is Open "
                "(likely wrong DOM element)",
                closed_days,
            )
            hours_by_day = HoursByDay()

    return Hours(
        is_open_now=is_open,
        current_status=status_text,
        hours_by_day=hours_by_day,
    )


def _parse_hours_aria(aria_text: str) -> HoursByDay:
    """
    Parse weekly hours from a button aria-label.

    Google Maps encodes hours in two formats:
      Format A: "Monday, 9 AM to 9 PM; Tuesday, ..."   (semicolon-separated)
      Format B: "Monday, 9 AM–9 PM, Tuesday, ..."       (comma-separated, en-dash range)
    Also handles "Closed" in place of hours for any day.
    """
    DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    data: dict[str, str] = {}

    if not aria_text:
        return HoursByDay(**data)

    # Normalise: replace en-dash with hyphen, collapse whitespace
    text = re.sub(r"\u2013|\u2014", "-", aria_text)
    text = re.sub(r"\s+", " ", text)

    # Split on semicolons OR on day-name boundaries (handles both formats)
    # Insert a virtual separator before each day name
    for day in DAYS:
        text = re.sub(rf"(?<=[^;]),\s*(?={day})", ";", text, flags=re.IGNORECASE)
    segments = [s.strip() for s in text.split(";") if s.strip()]

    for segment in segments:
        lower = segment.lower()
        for day in DAYS:
            if lower.startswith(day):
                hours_part = segment[len(day):].strip().lstrip(",:").strip()
                if hours_part:
                    data[day] = hours_part
                break

    logger.debug("  [hours] aria parse → %d days: %s", len(data), list(data.keys()))
    return HoursByDay(**data)


async def _extract_hours_via_js(page: Page) -> HoursByDay:
    """
    DOM-agnostic extraction of business hours after the hours panel is expanded.

    Strategy:
    1. Find the aria-expanded="true" button and check its aria-label (best source).
    2. Walk up the button's DOM tree to find the tightest container that holds all
       7 day names — this is the hours popup regardless of what class names Google uses.
    3. Inside that container, try a table-row parse, then a line-by-line parse.
    4. Validate each extracted value contains AM/PM or "Closed".
    """
    raw: str | None = await page.evaluate("""
        () => {
            const DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
            const DAYS_L = DAYS.map(d => d.toLowerCase());
            const TIME_RE = /[0-9].*?(?:AM|PM)|Closed/i;

            // ── Step 1: read aria-label of the expanded hours button ──────────
            // Look for any button/element that has aria-expanded="true" AND
            // whose aria-label contains day names (it IS the hours button).
            for (const el of document.querySelectorAll('[aria-expanded="true"]')) {
                const label = el.getAttribute('aria-label') || '';
                const count = DAYS.filter(d => label.includes(d)).length;
                if (count >= 5) {
                    return JSON.stringify({ source: 'aria', text: label });
                }
            }

            // ── Step 2: find the hours container by walking up from the button ─
            // The button we clicked is identified by data-item-id="oh" or its
            // container. Walk up looking for the tightest element with 5+ day names.
            const candidates = [
                ...document.querySelectorAll(
                    '[data-item-id="oh"], [aria-expanded="true"], ' +
                    '.t39EBf, .OMl5r, .eLasMc, .y0skZc, [data-section-id="Oh"]'
                )
            ];

            let hoursContainer = null;
            for (const seed of candidates) {
                let el = seed;
                for (let i = 0; i < 8; i++) {
                    if (!el) break;
                    const text = el.innerText || '';
                    const count = DAYS.filter(d => text.includes(d)).length;
                    if (count >= 5) {
                        // Found a good container — now look for the tightest child that
                        // still has 5+ day names (avoid getting the whole page body)
                        for (const child of el.querySelectorAll('*')) {
                            const ct = child.innerText || '';
                            const cc = DAYS.filter(d => ct.includes(d)).length;
                            if (cc >= 5 && ct.length < (el.innerText || '').length) {
                                el = child;
                            }
                        }
                        hoursContainer = el;
                        break;
                    }
                    el = el.parentElement;
                }
                if (hoursContainer) break;
            }

            if (!hoursContainer) {
                // Last resort: scan ALL elements for any that contain 5+ day names
                // and have reasonable text length (not the whole page)
                let best = null, bestScore = 0;
                document.querySelectorAll('div, ul, table, section').forEach(el => {
                    const text = el.innerText || '';
                    if (text.length > 5000 || text.length < 30) return;
                    const score = DAYS.filter(d => text.includes(d)).length;
                    if (score > bestScore) { bestScore = score; best = el; }
                });
                if (bestScore >= 5) hoursContainer = best;
            }

            if (!hoursContainer) return null;

            // ── Step 3a: table-row parse ──────────────────────────────────────
            const rows = hoursContainer.querySelectorAll('tr');
            if (rows.length >= 2) {
                const result = {};
                for (const row of rows) {
                    const cells = row.querySelectorAll('td, th');
                    if (cells.length < 2) continue;
                    const dayText = (cells[0].innerText || '').toLowerCase().trim();
                    // Gather all time text from second cell (handles nested li/span)
                    const timeText = (cells[1].innerText || '').trim()
                        .replace(/\\n/g, ', ').replace(/\\s+/g, ' ');
                    const matchedDay = DAYS_L.find(d => dayText.includes(d));
                    if (matchedDay && (TIME_RE.test(timeText) || /closed/i.test(timeText))) {
                        result[matchedDay] = timeText || 'Closed';
                    }
                }
                if (Object.keys(result).length >= 3) {
                    return JSON.stringify({ source: 'table', result });
                }
            }

            // ── Step 3b: line-by-line text parse ─────────────────────────────
            const lines = (hoursContainer.innerText || '')
                .split('\\n')
                .map(l => l.trim())
                .filter(l => l.length > 0);

            const result = {};
            for (let i = 0; i < lines.length; i++) {
                const lineLow = lines[i].toLowerCase();
                const matchedDay = DAYS_L.find(
                    d => lineLow === d
                      || lineLow.startsWith(d + ' ')
                      || lineLow.startsWith(d + ',')
                      || lineLow.startsWith(d + ':')
                );
                if (!matchedDay || result[matchedDay]) continue;

                // Time may be on the same line (after day name) or next line
                const rest = lines[i].slice(matchedDay.length).replace(/^[\\s,:]+/, '').trim();
                const nextLine = (i + 1 < lines.length) ? lines[i + 1].trim() : '';

                // Try same-line first, then next line
                for (const candidate of [rest, nextLine]) {
                    if (TIME_RE.test(candidate) || /^closed$/i.test(candidate)) {
                        result[matchedDay] = candidate;
                        break;
                    }
                }
            }

            if (Object.keys(result).length >= 2) {
                return JSON.stringify({ source: 'lines', result });
            }

            // ── Step 3c: raw text with regex as absolute last resort ──────────
            const rawText = hoursContainer.innerText || '';
            const fallback = {};
            for (const day of DAYS_L) {
                const m = rawText.match(
                    new RegExp(day + '[\\\\s,:\\\\n]+([^\\\\n]{3,30}(?:AM|PM|Closed)[^\\\\n]{0,20})', 'i')
                );
                if (m) fallback[day] = m[1].trim();
            }
            if (Object.keys(fallback).length >= 2) {
                return JSON.stringify({ source: 'regex', result: fallback });
            }

            return null;
        }
    """)

    if not raw:
        logger.debug("  [hours] JS extraction: no hours container found")
        return HoursByDay()

    try:
        parsed = json.loads(raw)
    except Exception as e:
        logger.debug("  [hours] JS extraction: JSON parse error: %s — raw: %r", e, raw[:200])
        return HoursByDay()

    source = parsed.get("source", "?")
    logger.debug("  [hours] JS extraction source=%r", source)

    # aria-label source — reuse the Python parser
    if source == "aria":
        result = _parse_hours_aria(parsed.get("text", ""))
        logger.debug("  [hours] JS aria parse → %d days", sum(1 for v in result.model_dump().values() if v))
        return result

    # table/lines/regex source — already a dict
    day_data: dict = parsed.get("result", {})
    # Validate each value before storing
    valid: dict[str, str] = {}
    for day, val in day_data.items():
        if val and (re.search(r"(?:AM|PM)", val, re.IGNORECASE) or re.search(r"closed", val, re.IGNORECASE)):
            valid[day] = val
    logger.debug("  [hours] JS %s parse → %d valid days: %s", source, len(valid), list(valid.keys()))
    return HoursByDay(**valid)


async def _extract_description(page: Page) -> str | None:
    logger.debug("  [description] trying %d selectors…", len(DESCRIPTION_SELECTORS))

    # Google Maps truncates descriptions behind a "See more" button.
    # Click it first so the full text is in the DOM.
    _SEE_MORE_SELECTORS = [
        'button[aria-label*="See more"]',
        'button[aria-label*="see more"]',
        'button[jsaction*="description.expand"]',
        'button[aria-expanded="false"].w8nwRe',
        '.W4Efsd button[aria-expanded="false"]',
        'button[data-expandable-section] ~ button',
    ]
    for sel in _SEE_MORE_SELECTORS:
        try:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(200)  # reduced from 400ms
                logger.debug("  [description] clicked 'See more' via %r", sel)
                break
        except Exception:
            pass  # not present — continue

    text = await first_text(page, DESCRIPTION_SELECTORS)
    if text and _is_valid_description(text):
        return text
    if text:
        logger.debug("  [description] primary selector returned junk %r — trying fallback", text[:60])

    # ── Click the About tab — description is ONLY in the DOM when About tab is active ──
    # Google Maps restaurants almost never show description on the Overview tab.
    about_clicked = False
    for sel in ABOUT_TAB_SELECTORS:
        try:
            tab = await page.query_selector(sel)
            if tab and await tab.is_visible():
                await tab.click()
                await page.wait_for_timeout(700)  # reduced from 1200ms
                logger.debug("  [description] clicked About tab via %r", sel)
                about_clicked = True
                break
        except Exception:
            continue

    if not about_clicked:
        # Fallback: find the About tab by its visible text label
        try:
            all_tabs = await page.query_selector_all(
                'button[role="tab"], .hh2c6, [role="tablist"] button'
            )
            for btn in all_tabs:
                btn_text = (await get_text(btn) or "").strip().lower()
                if btn_text == "about" or btn_text.startswith("about"):
                    await btn.click()
                    await page.wait_for_timeout(700)  # reduced from 1200ms
                    logger.debug("  [description] About tab clicked via text scan: %r", btn_text)
                    about_clicked = True
                    break
        except Exception:
            pass

    if about_clicked:
        # Re-try primary selectors — some layouts expose description once About is active
        text = await first_text(page, DESCRIPTION_SELECTORS)
        if text and _is_valid_description(text):
            logger.debug("  [description] found after About tab click via primary selectors")
            return text

    # ── Try About-tab specific selectors ──────────────────────────────────────
    # NOTE: .HlvSq is intentionally excluded — it matches the compact "4.3 Fine dining·"
    # rating+category line in Google Maps, not a real business description.
    _ABOUT_DESC_SELECTORS = [
        '.WeS02d span',
        '.LBgpqf',
        'div[data-attrid*="description"] span',
        '[data-section-id="description"] span',
        # Newer Google Maps layouts
        '.iP2t7d .PYvSYb',
        '.iP2t7d p',
        '.iP2t7d .fontBodyMedium',
        '.m6QErb[aria-label*="About"] p',
        '.m6QErb[aria-label*="About"] span.fontBodyMedium',
        # Any paragraph-length text inside the About panel
        '.iP2t7d span',
        '.iP2t7d div.fontBodyMedium',
        'div[aria-label*="About"] span',
        'div[aria-label*="About"] p',
    ]
    for sel in _ABOUT_DESC_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el:
                text = await get_text(el)
                if text and _is_valid_description(text):
                    logger.debug("  [description] found via About-specific selector %r: %d chars", sel, len(text))
                    return text
        except Exception:
            continue

    # Last resort: JS scan for the longest paragraph-like text in the About section
    try:
        desc_js: str | None = await page.evaluate("""
            () => {
                // Find all text nodes that look like prose (>= 80 chars, contains spaces)
                const candidates = [];
                const els = document.querySelectorAll('p, span.fontBodyMedium, div.PYvSYb, span.PYvSYb');
                for (const el of els) {
                    const text = (el.innerText || '').trim();
                    if (text.length >= 30 && text.includes(' ') && text.split(' ').length >= 5) {
                        // Exclude rating-like strings (start with a digit)
                        if (!/^\\d/.test(text)) {
                            candidates.push(text);
                        }
                    }
                }
                // Return the longest candidate
                if (candidates.length === 0) return null;
                return candidates.reduce((a, b) => a.length >= b.length ? a : b);
            }
        """)
        if desc_js and _is_valid_description(desc_js):
            logger.debug("  [description] JS scan found %d-char description", len(desc_js))
            return desc_js
    except Exception as e:
        logger.debug("  [description] JS scan error: %s", e)

    return None


def _is_valid_description(text: str) -> bool:
    """
    Return True only if text looks like a real business description.

    Rejects:
      - Empty or short strings (< 30 chars)
      - Accessibility / amenity chip text (starts with checkmark icon \ue5ca or ✔/✓)
      - Attribute phrases: "Wheelchair accessible entrance", "Assisted listening devices"
      - Listing freshness: "Updated/Confirmed by this business N weeks ago"
      - Google Maps' compact info line: "4.3 Fine dining restaurant·"
      - Pure category strings without prose
    """
    if not text or len(text.strip()) < 30:
        return False
    t = text.strip()

    # Reject checkmark icon prefix — Material Icons \ue5ca, ✔, ✓, ✅
    # Google Maps attribute chips always start with this icon.
    if t[0] in ('\ue5ca', '✔', '✓', '✅', '☑'):
        return False

    # Reject "Updated/Confirmed by this business X [days|weeks|months] ago"
    if re.search(r"(updated|confirmed) by this business", t, re.IGNORECASE):
        return False

    # Reject "4.5 Category name·" — starts with a rating number followed by a word
    if re.match(r"^\d+\.\d+\s+\w", t):
        return False

    # Reject accessibility / amenity attribute text
    if re.search(
        r"\b(wheelchair|accessible|accessibility|hearing loop|listening device"
        r"|parking lot|parking garage|restroom|assisted listening)\b",
        t, re.IGNORECASE,
    ):
        return False

    # Reject strings that are purely a category (no sentence structure)
    if re.match(r"^[\w\s&-]+(restaurant|café|cafe|bar|lounge|bistro|brasserie)[\s·•]*$", t, re.IGNORECASE):
        return False

    return True


async def _extract_price(page: Page) -> str | None:
    logger.debug("  [price] trying %d selectors…", len(PRICE_SELECTORS))
    for selector in PRICE_SELECTORS:
        try:
            el = await page.query_selector(selector)
            if el:
                aria = await get_attr(el, "aria-label")
                if aria:
                    # aria-label may say "Price: Inexpensive" or "Inexpensive" or "$$ · Price"
                    # Normalise it: extract the dollar signs or the price tier word
                    cleaned = _normalise_price(aria)
                    if cleaned:
                        logger.debug("  [price] from aria-label via %r: %r → %r", selector, aria, cleaned)
                        return cleaned
                text = await get_text(el)
                if text:
                    cleaned = _normalise_price(text)
                    if cleaned:
                        logger.debug("  [price] from text via %r: %r → %r", selector, text, cleaned)
                        return cleaned
        except Exception as e:
            logger.debug("  [price] selector %r error: %s", selector, e)

    # Fallback A: scan ALL buttons/spans on the page for price tier keywords
    # (Google sometimes renders price as a chip near the category without a stable class)
    try:
        all_buttons = await page.query_selector_all("button, span.mgr77e, .DkEaL ~ span")
        for btn in all_buttons[:30]:
            aria = await get_attr(btn, "aria-label") or ""
            text = (await get_text(btn) or "")
            for candidate in (aria, text):
                cleaned = _normalise_price(candidate)
                if cleaned:
                    logger.debug("  [price] button scan hit: %r → %r", candidate, cleaned)
                    return cleaned
    except Exception as e:
        logger.debug("  [price] button scan error: %s", e)

    # Fallback B: Comprehensive JavaScript scan — covers every known Google Maps
    # price rendering pattern regardless of dynamic class names.
    try:
        price_js: str | None = await page.evaluate("""
            () => {
                const TIER_WORDS = ['Very expensive', 'Expensive', 'Moderately expensive', 'Inexpensive'];
                const TIER_SYMS  = {
                    'Very expensive': '$$$$', 'Expensive': '$$$',
                    'Moderately expensive': '$$', 'Inexpensive': '$'
                };

                // ── Method 1: aria-label with tier words (most reliable) ──────────
                for (const el of document.querySelectorAll('[aria-label]')) {
                    const label = el.getAttribute('aria-label') || '';
                    for (const tier of TIER_WORDS) {
                        if (label.includes(tier)) return TIER_SYMS[tier];
                    }
                    // e.g. aria-label="Price: $$" or "Price · $$"
                    if (/[$]{1,4}/.test(label) && /price/i.test(label)) {
                        const m = label.match(/[$]{1,4}/);
                        if (m) return m[0];
                    }
                }

                // ── Method 2: parent of the category button (subheader row) ──────
                // Google renders "Category · price" in the same row container
                const catEl = document.querySelector(
                    '.DkEaL, button[jsaction*="category"], .mgr77e, button[aria-label*="category" i]'
                );
                if (catEl) {
                    let parent = catEl.parentElement;
                    for (let i = 0; i < 5; i++) {
                        if (!parent) break;
                        const text = (parent.innerText || '');
                        // Stay in the subheader region (< 300 chars) to avoid false positives
                        if (text.length < 300) {
                            const m = text.match(/[$]{1,4}/);
                            if (m) return m[0];
                        }
                        parent = parent.parentElement;
                    }
                }

                // ── Method 3: walk up from h1 — price is always near the name ───
                const h1 = document.querySelector('h1');
                if (h1) {
                    let container = h1.parentElement;
                    for (let i = 0; i < 6; i++) {
                        if (!container) break;
                        // Only examine the first few lines so we don't scan the whole page
                        const firstLines = (container.innerText || '').split('\\n').slice(0, 8).join(' ');
                        if (firstLines.length < 400) {
                            const m = firstLines.match(/[$]{1,4}/);
                            if (m) return m[0];
                        }
                        container = container.parentElement;
                    }
                }

                // ── Method 4: any element whose ENTIRE text is 1-4 dollar signs ─
                for (const el of document.querySelectorAll('span, div, button')) {
                    const text = (el.textContent || '').trim();
                    if (/^[$]{1,4}$/.test(text)) return text;
                }

                // ── Method 5: scan the top of role="main" for · $$ pattern ──────
                const mainEl = document.querySelector('[role="main"]');
                if (mainEl) {
                    const firstChunk = (mainEl.innerText || '').substring(0, 400);
                    // "Category · $$" or "$$ · Category"
                    const m = firstChunk.match(/\u00b7\\s*([$]{1,4})(?:\\s|\u00b7|$)|([$]{1,4})\\s*\u00b7/);
                    if (m) return (m[1] || m[2]);
                    // Plain "$$" anywhere in first 400 chars
                    const m2 = firstChunk.match(/[$]{1,4}/);
                    if (m2) return m2[0];
                }

                // ── Method 6: data-attrid containing price info ──────────────────
                for (const el of document.querySelectorAll('[data-attrid*="price" i], [data-attrid*="Price"]')) {
                    const text = (el.innerText || '').trim();
                    if (text) return text;
                }

                // ── Method 7: scan raw page HTML for price data in embedded JSON ──
                // Google Maps embeds initialisation JSON containing "price_range" or
                // "priceRange" keys whose value is 1-4 (maps to $-$$$$).
                const PRICE_MAP = { '1': '$', '2': '$$', '3': '$$$', '4': '$$$$' };
                const html = document.documentElement.innerHTML;
                // "price_range":2  or  "priceRange":2  (integer 1-4)
                let pm = html.match(/"price_?[Rr]ange"\\s*:\\s*([1-4])(?:[^0-9]|$)/);
                if (pm) return PRICE_MAP[pm[1]];
                // price_level keyword followed by a digit
                pm = html.match(/"price_?[Ll]evel"\\s*:\\s*([1-4])(?:[^0-9]|$)/);
                if (pm) return PRICE_MAP[pm[1]];
                // Tier words inside JSON strings
                const TIER_WORDS2 = ['Very expensive','Expensive','Moderately expensive','Inexpensive'];
                const TIER_SYMS2  = {
                    'Very expensive':'$$$$','Expensive':'$$$',
                    'Moderately expensive':'$$','Inexpensive':'$'
                };
                for (const tier of TIER_WORDS2) {
                    if (html.includes('"' + tier + '"') || html.includes("'" + tier + "'")) {
                        return TIER_SYMS2[tier];
                    }
                }

                return null;
            }
        """)
        if price_js:
            cleaned = _normalise_price(price_js)
            if cleaned:
                logger.debug("  [price] JS scan hit: %r → %r", price_js, cleaned)
                return cleaned
    except Exception as e:
        logger.debug("  [price] JS scan error: %s", e)

    return None


def _normalise_price(raw: str) -> str | None:
    """
    Extract a clean price level string from raw text or aria-label.

    Recognises:
      - Dollar signs directly: "$", "$$", "$$$", "$$$$"
      - Google's tier names: "Inexpensive", "Moderately expensive", "Expensive", "Very expensive"
      - Price prefixes: "Price: $$" or "Price: Inexpensive"
    Returns the dollar-sign representation, or None if no price info found.
    """
    if not raw:
        return None
    raw = raw.strip()

    # Extract dollar signs first (most useful for consumers)
    dollar_match = re.search(r'(\${1,4})(?:\s|$|·)', raw)
    if dollar_match:
        return dollar_match.group(1)

    # Also accept "$" if it's the entire text or appears after "Price:"
    if re.search(r'Price:\s*(\${1,4})', raw, re.IGNORECASE):
        m = re.search(r'Price:\s*(\${1,4})', raw, re.IGNORECASE)
        return m.group(1) if m else None

    # Map tier names to dollar signs
    tier_map = {
        "inexpensive": "$",
        "moderately expensive": "$$",
        "expensive": "$$$",
        "very expensive": "$$$$",
    }
    lower = raw.lower()
    for tier, symbol in tier_map.items():
        if tier in lower:
            return symbol

    return None


async def _extract_images(page: Page) -> Images:
    from models.business import Images as ImagesModel

    logger.debug("  [images] extracting main image…")
    urls: list[str] = []

    main_el = await first_element(page, MAIN_IMAGE_SELECTORS)
    main_url: str | None = None
    if main_el:
        src = await get_attr(main_el, "src")
        if src and src.startswith("http"):
            src = _upsize_image_url(src)
            main_url = src
            urls.append(src)
            logger.debug("  [images] main image: %s…", src[:80])
    else:
        logger.debug("  [images] main image selector: no match")

    logger.debug("  [images] collecting all photo thumbnails…")
    for selector in ALL_PHOTOS_SELECTORS:
        if len(urls) >= MAX_IMAGES:
            break
        try:
            imgs = await page.query_selector_all(selector)
            if not imgs:
                continue
            logger.debug("  [images] found %d img elements via %r", len(imgs), selector)
            for img in imgs:
                if len(urls) >= MAX_IMAGES:
                    break
                src = await get_attr(img, "src")
                if not src or not src.startswith("http"):
                    continue
                src = _upsize_image_url(src)
                if src in urls:
                    continue
                # Skip tiny thumbnail/avatar images (placeholders, not real business photos)
                if _is_tiny_image_url(src):
                    logger.debug("  [images] skipped tiny image: %s…", src[:80])
                    continue
                urls.append(src)
        except Exception as e:
            logger.debug("  [images] selector %r error: %s", selector, e)

    # Fallback: multi-strategy JS scan for all Google-hosted business photos.
    # Strategy A: <img> src attributes
    # Strategy B: CSS background-image (Google Maps photo strip uses these, not <img>)
    # Strategy C: raw HTML source scan — finds URLs embedded in JSON/script data
    if len(urls) < MAX_IMAGES:
        try:
            js_urls: list[str] = await page.evaluate("""
                (maxImages) => {
                    const seen = new Set();
                    const result = [];

                    function add(url) {
                        if (!url || !url.startsWith('http')) return;
                        if (!url.includes('googleusercontent.com')) return;
                        // Skip tiny images (≤100px) based on =wW-hH URL params
                        const m = url.match(/=w(\\d+)-h(\\d+)/);
                        if (m && (parseInt(m[1]) <= 100 || parseInt(m[2]) <= 100)) return;
                        // Normalise: strip trailing junk after the size param
                        const clean = url.split(/["'\\s<>]/)[0];
                        if (!seen.has(clean)) { seen.add(clean); result.push(clean); }
                    }

                    // A: <img> src attributes
                    for (const img of document.querySelectorAll('img')) {
                        add(img.src);
                        if (result.length >= maxImages) return result;
                    }

                    // B: CSS background-image on any element
                    for (const el of document.querySelectorAll('[style*="googleusercontent"]')) {
                        const style = el.getAttribute('style') || '';
                        const m = style.match(/url\\("?(https:[^"')\\s]+)"?\\)/);
                        if (m) add(m[1]);
                        if (result.length >= maxImages) return result;
                    }

                    // C: raw HTML source — finds photos embedded in JSON / data attrs
                    const html = document.documentElement.innerHTML;
                    const re = /https:\\/\\/(?:lh\\d+)\\.googleusercontent\\.com\\/[^"'\\s\\\\<>]{20,}/g;
                    let hit;
                    while ((hit = re.exec(html)) !== null) {
                        // Decode common JSON-escaped sequences
                        let url = hit[0]
                            .replace(/\\\\u003d/g, '=')
                            .replace(/\\\\u0026/g, '&')
                            .replace(/\\\\n/g, '')
                            .split(/["'<>\\\\]/)[0];
                        add(url);
                        if (result.length >= maxImages) break;
                    }

                    return result;
                }
            """, MAX_IMAGES)
            before = len(urls)
            for js_src in js_urls:
                js_src = _upsize_image_url(js_src)
                if js_src not in urls:
                    urls.append(js_src)
                if len(urls) >= MAX_IMAGES:
                    break
            logger.debug("  [images] JS scan added %d extra images", len(urls) - before)
        except Exception as e:
            logger.debug("  [images] JS scan error: %s", e)

    logger.debug("  [images] total: %d URLs collected (max=%d)", len(urls), MAX_IMAGES)
    return ImagesModel(
        main_image_url=main_url or (urls[0] if urls else None),
        all_image_urls=urls[:MAX_IMAGES],
    )


def _is_tiny_image_url(url: str) -> bool:
    """
    Return True if the URL is a tiny thumbnail (≤ 100 px in either dimension).

    Google image URLs encode dimensions as '=wW-hH' (e.g. '=w32-h32-p-k-no').
    Tiny images are typically profile picture placeholders, not real business photos.
    """
    m = re.search(r"=w(\d+)-h(\d+)", url)
    if m:
        w, h = int(m.group(1)), int(m.group(2))
        return w <= 100 or h <= 100
    return False


def _upsize_image_url(url: str) -> str:
    """
    Replace Google CDN size parameters to request a high-quality image.

    Google's image hosting (lh3.googleusercontent.com) accepts size overrides via
    the URL suffix.  The scraper often gets '=w112-h112-p-k-no' thumbnails; by
    rewriting to '=w1200-h900-p-k-no' we get a full-resolution version.
    Only rewrites URLs that already contain a recognised size suffix.
    """
    return re.sub(r"=w\d+-h\d+[-\w]*$", "=w1200-h900-p-k-no", url)


async def _extract_reviews(page: Page) -> list[Review]:
    # Reviews are on a separate tab — click it first, then wait for content to load.
    # Without this click, review elements are not in the DOM.
    logger.debug("  [reviews] clicking Reviews tab (%d selectors)…", len(REVIEWS_TAB_SELECTORS))
    tab_clicked = False

    # Primary: try CSS selectors
    for sel in REVIEWS_TAB_SELECTORS:
        try:
            tab = await page.query_selector(sel)
            if tab and await tab.is_visible():
                await tab.click()
                logger.debug("  [reviews] Reviews tab clicked via %r", sel)
                tab_clicked = True
                break
        except Exception as e:
            logger.debug("  [reviews] tab selector %r failed: %s", sel, e)

    # Fallback: click by button text content (most reliable across layout changes)
    if not tab_clicked:
        try:
            tab = page.get_by_role("tab", name=re.compile(r"reviews?", re.IGNORECASE)).first
            if await tab.is_visible():
                await tab.click()
                logger.debug("  [reviews] Reviews tab clicked via get_by_role(tab, 'reviews')")
                tab_clicked = True
        except Exception as e:
            logger.debug("  [reviews] get_by_role tab click failed: %s", e)

    # Fallback 2: find tab buttons by text
    if not tab_clicked:
        try:
            all_tabs = await page.query_selector_all('button[role="tab"], .hh2c6, [role="tablist"] button')
            for btn in all_tabs:
                text = (await get_text(btn) or "").lower()
                if "review" in text:
                    await btn.click()
                    logger.debug("  [reviews] Reviews tab clicked via text scan: %r", text)
                    tab_clicked = True
                    break
        except Exception as e:
            logger.debug("  [reviews] text-scan tab click failed: %s", e)

    if not tab_clicked:
        logger.debug("  [reviews] could not click Reviews tab — reviews may not load")

    if tab_clicked:
        # Wait for review cards to appear
        for review_sel in REVIEW_ITEM_SELECTORS:
            try:
                await page.wait_for_selector(review_sel, timeout=4000)
                logger.debug("  [reviews] review element visible: %r", review_sel)
                break
            except Exception:
                continue
        await page.wait_for_timeout(500)  # reduced from 800ms

        # Scroll the panel to trigger lazy-loading of review cards
        try:
            panel = await page.query_selector('div[role="main"]')
            if not panel:
                panel = await page.query_selector('.m6QErb[aria-label]')
            if panel:
                await panel.evaluate("el => el.scrollTop += 600")
                await page.wait_for_timeout(300)  # reduced from 500ms
        except Exception as e:
            logger.debug("  [reviews] panel scroll failed: %s", e)

    logger.debug("  [reviews] looking for review items (%d selectors)…", len(REVIEW_ITEM_SELECTORS))
    review_items = await all_elements(page, REVIEW_ITEM_SELECTORS)

    # If CSS selectors found nothing, try JS to find review containers
    if not review_items and tab_clicked:
        try:
            js_count: int = await page.evaluate("""
                () => {
                    // Common review card signatures: elements with star ratings inside them
                    const candidates = document.querySelectorAll('[data-review-id], .jftiEf, .GHT2ce, .lRecsd');
                    return candidates.length;
                }
            """)
            logger.debug("  [reviews] JS scan found %d potential review containers", js_count)
        except Exception:
            pass

    sample = review_items[:MAX_REVIEWS_SAMPLE]
    logger.debug(
        "  [reviews] found %d total review elements, sampling %d",
        len(review_items), len(sample),
    )

    # Extract the total review count from the Reviews panel header.
    # When the Reviews tab loads, Google shows the displayed count (e.g. "268 reviews")
    # in the panel heading — this is more reliable than the main-page count element
    # because it renders even when the overview count (.lyplG) doesn't.
    panel_review_count: int | None = None
    if tab_clicked:
        try:
            panel_count_raw: str | None = await page.evaluate("""
                () => {
                    // Common panel-header selectors (class names vary by layout)
                    const candidates = [
                        document.querySelector('.jANrlb .fontDisplayLarge'),
                        document.querySelector('.jANrlb .fontHeadlineLarge'),
                        document.querySelector('h2.fontHeadlineLarge'),
                        document.querySelector('[data-review-count]'),
                    ];
                    for (const el of candidates) {
                        if (!el) continue;
                        const t = (el.innerText || '').trim();
                        if (/^[\\d,]+$/.test(t)) return t;
                    }

                    // Scan h2/h3 elements for a standalone number (the panel count)
                    for (const el of document.querySelectorAll('h2, h3')) {
                        const t = (el.innerText || '').trim();
                        if (/^[\\d,]+$/.test(t) && parseInt(t.replace(/,/g,'')) > 0) return t;
                    }

                    // Scan for "N reviews" text anywhere in the reviews panel area
                    const panel = document.querySelector('.m6QErb[aria-label], [role="main"] .m6QErb');
                    if (panel) {
                        const m = (panel.innerText || '').match(/([\\d,]+)\\s+reviews?/i);
                        if (m) return m[1];
                    }

                    return null;
                }
            """)
            if panel_count_raw:
                clean = panel_count_raw.replace(",", "")
                if clean.isdigit():
                    panel_review_count = int(clean)
                    logger.debug("  [reviews] panel count: %d", panel_review_count)
        except Exception as e:
            logger.debug("  [reviews] panel count extraction error: %s", e)

    reviews: list[Review] = []
    for i, item in enumerate(sample, start=1):
        try:
            author = await _first_text_in(item, REVIEW_AUTHOR_SELECTORS)
            rating_el = await _first_el_in(item, REVIEW_RATING_SELECTORS)
            rating_text = await get_attr(rating_el, "aria-label") if rating_el else None
            rating = parse_rating_text(rating_text)
            text_el = await _first_el_in(item, REVIEW_TEXT_SELECTORS)
            text = await get_text(text_el) if text_el else None
            date_el = await _first_el_in(item, REVIEW_DATE_SELECTORS)
            date = await get_text(date_el) if date_el else None

            logger.debug(
                "  [reviews] #%d: author=%r rating=%s text=%s date=%r",
                i, author, rating,
                f"{len(text)} chars" if text else "None",
                date,
            )

            if author or text:
                reviews.append(Review(author=author, rating=rating, text=text, date=date))
        except Exception as e:
            logger.debug("  [reviews] #%d: extraction error: %s", i, e)

    return reviews, panel_review_count


async def _extract_attributes(page: Page) -> Attributes:
    from models.business import Attributes as AttrModel

    logger.debug("  [attributes] clicking About tab to reveal amenity section…")

    # Amenities/attributes live under the "About" tab, not the Overview tab.
    # We must click About first — otherwise the DOM has no attribute chips at all.
    about_clicked = False
    for sel in ABOUT_TAB_SELECTORS:
        try:
            tab = await page.query_selector(sel)
            if tab and await tab.is_visible():
                await tab.click()
                await page.wait_for_timeout(600)  # reduced from 1500ms — tab is usually already active after _extract_description
                logger.debug("  [attributes] About tab clicked via %r", sel)
                about_clicked = True
                break
        except Exception as e:
            logger.debug("  [attributes] About tab selector %r failed: %s", sel, e)

    if not about_clicked:
        logger.debug("  [attributes] About tab not found — trying attribute selectors anyway")

    data: dict[str, list[str]] = {
        "amenities": [], "accessibility": [], "payments_accepted": [],
        "service_options": [], "highlights": [], "crowd": [], "planning": [],
    }

    for sel in ATTRIBUTE_ITEM_SELECTORS:
        try:
            items = await page.query_selector_all(sel)
            if not items:
                continue
            raw: list[str] = []
            for item in items:
                text = await get_text(item)
                if text:
                    raw.append(text)

            # Extra guard: strip() each text and skip empty/whitespace-only entries
            # (icon spans sometimes produce invisible chars that survive get_text).
            clean_candidates = [
                t for t in raw
                if t.strip() and not _is_garbage_attribute(t)
            ]
            # Deduplicate while preserving first-occurrence order
            clean = list(dict.fromkeys(clean_candidates))
            if clean:
                data["amenities"] = clean
                logger.debug(
                    "  [attributes] %d valid tags (filtered %d garbage, deduped) via %r: %s",
                    len(clean), len(raw) - len(clean), sel, clean[:5],
                )
                break
            elif raw:
                logger.debug("  [attributes] %r matched %d items but all filtered as garbage", sel, len(raw))
        except Exception as e:
            logger.debug("  [attributes] selector %r error: %s", sel, e)

    if not data["amenities"]:
        logger.debug("  [attributes] no amenity tags found")
    else:
        # Categorise flat amenities list into structured sub-fields.
        # Google Maps renders all attributes together; we split them by keyword.
        _categorise_attributes(data)

    return AttrModel(**data)


# Strings that are definitely not amenities but appear in the same area of the page
_GARBAGE_ATTRIBUTE_STRINGS: frozenset[str] = frozenset({
    # UI action buttons
    "find a table", "place an order", "reserve a table", "order online",
    "add a photo", "suggest an edit", "share", "save", "nearby",
    "view all", "see all", "more", "directions", "send to phone",
    # Google Maps "Explore nearby" suggestion chips — these appear at the bottom of some
    # listing pages and are NOT the business's own amenities/attributes
    "nearby restaurants", "hotels", "things to do", "bars", "coffee",
    "takeout", "groceries", "attractions", "shopping", "nightlife",
    "gas stations", "pharmacies", "banks", "atms", "museums", "parks",
    "gyms", "spas", "hospitals", "clinics", "schools",
})

# Regex patterns for obvious non-amenity content
_PHONE_LIKE   = re.compile(r"^\+[\d\s\-\.\(\)]{6,}$")
_DOMAIN_LIKE  = re.compile(r"^[\w.-]+\.[a-z]{2,6}(/\S*)?$", re.IGNORECASE)
_PLUS_CODE    = re.compile(r"^[A-Z0-9]{4,6}\+[A-Z0-9]{2,4}", re.IGNORECASE)
_FLOOR_PREFIX = re.compile(r"^floor\s+\d", re.IGNORECASE)


def _is_garbage_attribute(text: str) -> bool:
    """Return True if this string is NOT a real amenity/attribute chip label."""
    t = text.strip()
    # Empty strings (icon elements with no text content)
    if not t:
        return True
    # Too long to be a short attribute label
    if len(t) > 60:
        return True
    # Known UI action buttons
    if t.lower() in _GARBAGE_ATTRIBUTE_STRINGS:
        return True
    # Looks like a phone number
    if _PHONE_LIKE.match(t):
        return True
    # Looks like a bare domain / URL (e.g. "bombayborough.com", "bit.ly")
    if _DOMAIN_LIKE.match(t):
        return True
    # Looks like a Google Plus Code (e.g. "677J+HW Dubai")
    if _PLUS_CODE.match(t):
        return True
    # "Located in: ..." — location context, not an amenity
    if t.lower().startswith("located in:"):
        return True
    # "Floor N · ..." — building location info
    if _FLOOR_PREFIX.match(t):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Attribute categorisation
# ─────────────────────────────────────────────────────────────────────────────

# Keywords (lowercase) that identify each sub-category.
# An amenity whose lowercased value contains any of these words is moved to
# the corresponding sub-field AND kept in the flat amenities list.
_ACCESSIBILITY_KW: frozenset[str] = frozenset({
    "wheelchair", "accessible", "hearing loop", "assistive", "listening device",
})
_PAYMENTS_KW: frozenset[str] = frozenset({
    "credit card", "debit card", "nfc mobile", "cash only", "checks",
})
_SERVICE_OPTIONS_KW: frozenset[str] = frozenset({
    "dine-in", "delivery", "takeout", "take-out", "no-contact",
    "curbside", "in-store shopping", "onsite service",
})
_HIGHLIGHTS_KW: frozenset[str] = frozenset({
    "great coffee", "great dessert", "great tea", "live music",
    "rooftop seating", "outdoor seating", "happy hour",
    "bar onsite", "fireplace", "waterfront",
})
_CROWD_KW: frozenset[str] = frozenset({
    "family-friendly", "groups", "tourists", "college student",
    "solo dining", "lgbtq", "kids",
})
_PLANNING_KW: frozenset[str] = frozenset({
    "reservation", "appointment",
})


def _categorise_attributes(data: dict[str, list[str]]) -> None:
    """
    Populate structured sub-fields (accessibility, payments_accepted, etc.)
    from the flat amenities list, using keyword matching.

    Items are placed in sub-fields AND kept in the flat amenities list so that
    callers can use whichever representation they prefer.
    """
    kw_map = [
        ("accessibility",      _ACCESSIBILITY_KW),
        ("payments_accepted",  _PAYMENTS_KW),
        ("service_options",    _SERVICE_OPTIONS_KW),
        ("highlights",         _HIGHLIGHTS_KW),
        ("crowd",              _CROWD_KW),
        ("planning",           _PLANNING_KW),
    ]
    for tag in data.get("amenities", []):
        t_lower = tag.lower()
        for field, keywords in kw_map:
            if any(kw in t_lower for kw in keywords):
                if tag not in data[field]:
                    data[field].append(tag)
                break  # assign to first matching category only


# ─────────────────────────────────────────────────────────────────────────────
# Scoped element helpers (for review cards)
# ─────────────────────────────────────────────────────────────────────────────

async def _first_text_in(parent, selectors: list[str]) -> str | None:
    for sel in selectors:
        try:
            el = await parent.query_selector(sel)
            if el:
                text = await get_text(el)
                if text:
                    return text
        except Exception:
            continue
    return None


async def _first_el_in(parent, selectors: list[str]):
    for sel in selectors:
        try:
            el = await parent.query_selector(sel)
            if el:
                return el
        except Exception:
            continue
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Business summary banner (shown after each successful scrape)
# ─────────────────────────────────────────────────────────────────────────────

def _log_business_summary(b: Business, elapsed: float) -> None:
    """Log a concise one-line summary with key fields — easy to grep in the log file."""
    phone   = b.contact.phone   or "—"
    email   = b.contact.email   or "—"
    website = "✓" if b.contact.website else "—"
    rating  = f"{b.ratings.average_rating}" if b.ratings.average_rating else "—"
    reviews = f"{b.ratings.total_reviews}"  if b.ratings.total_reviews  else "—"
    lat     = f"{b.coordinates.latitude:.4f}"  if b.coordinates.latitude  else "—"
    lng     = f"{b.coordinates.longitude:.4f}" if b.coordinates.longitude else "—"

    logger.info(
        "✓ SCRAPED [%.1fs] | %r | phone=%s | email=%s | web=%s | rating=%s (%s reviews) | coords=(%s,%s)",
        elapsed,
        b.business_name,
        phone, email, website, rating, reviews, lat, lng,
    )
