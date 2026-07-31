"""
Data validation and normalisation.

Every decision is logged at DEBUG so you can see exactly why a value was
accepted or rejected without adding print statements.
"""

from __future__ import annotations

import html
import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Compiled patterns
# ─────────────────────────────────────────────────────────────────────────────

_PHONE_RE   = re.compile(r"^\+?[\d\s\-\(\)\.ext]{7,25}$", re.IGNORECASE)
_EMAIL_RE   = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_EMAIL_SCAN = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_CF_EMAIL_RE = re.compile(r'data-cfemail=["\']([0-9a-fA-F]+)["\']')
_OBFUSCATED_AT_RE = re.compile(r"\s*(?:\[|\()?(?:at|AT)(?:\]|\))?\s*")
_OBFUSCATED_DOT_RE = re.compile(r"\s*(?:\[|\()?(?:dot|DOT)(?:\]|\))?\s*")

# TLDs that are image/binary/code file extensions — never valid email TLDs.
# These appear in regex matches when email-like patterns occur in image filenames
# (e.g. "artboard-1dx@0.5x.png" matches the email regex but ".png" is not a TLD).
_EMAIL_BLOCKED_TLDS: frozenset[str] = frozenset({
    # Image formats
    "png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "bmp", "tiff", "tif",
    "avif", "heic", "heif", "raw",
    # Retina/density suffixes that appear after dots (e.g. "@2x.png" → "2x")
    "2x", "3x", "4x", "5x", "0x", "1x",
    # Binary / archive formats
    "pdf", "zip", "tar", "gz", "rar", "7z", "exe", "dll", "dmg", "pkg",
    # Media formats
    "mp4", "mp3", "avi", "mov", "mkv", "wav", "flac",
    # Source code extensions
    "css", "js", "ts", "py", "rb", "go", "rs", "java", "php", "sh", "bat",
    # Data formats
    "json", "xml", "csv", "yml", "yaml", "toml",
})

_EMAIL_JUNK_DOMAINS: frozenset[str] = frozenset({
    "example.com", "domain.com", "email.com", "yoursite.com",
    "website.com", "test.com",
    # Error-tracking / infrastructure — never real business emails
    "sentry.io", "sentry.wixpress.com",
    "ingest.sentry.io",
    "amazonaws.com", "s3.amazonaws.com",
    "mailchimp.com", "mandrillapp.com",
    "sendgrid.net", "mailgun.org",
    "googlegroups.com", "googlemail.com",
    # Website builders — contact forms, not direct emails
    "wix.com", "wixpress.com", "squarespace.com",
    "webflow.io", "wordpress.com", "shopify.com",
    # Restaurant booking / reservation platforms — not the restaurant's own email
    "sevenrooms.com", "opentable.com", "resy.com",
    "eatapp.co", "thefork.com", "bookatable.com",
})

# Social media domains that should never be stored as the business website field.
# A business may list its Instagram as its "website" on Google Maps — we detect and
# store that in social_media instead, leaving contact.website null.
_SOCIAL_MEDIA_DOMAINS: frozenset[str] = frozenset({
    "facebook.com", "fb.com",
    "instagram.com",
    "twitter.com", "x.com",
    "linkedin.com",
    "youtube.com", "youtu.be",
    "tiktok.com",
    "pinterest.com",
    "snapchat.com",
    "t.me", "telegram.me",
    "wa.me", "whatsapp.com",
    "threads.net",
})


# ─────────────────────────────────────────────────────────────────────────────
# Validators
# ─────────────────────────────────────────────────────────────────────────────

def validate_phone(phone: str | None) -> str | None:
    if not phone:
        logger.debug("validate_phone: input is empty — skipping")
        return None
    cleaned = phone.strip()
    if _PHONE_RE.match(cleaned):
        logger.debug("validate_phone: ACCEPTED %r", cleaned)
        return cleaned
    logger.debug("validate_phone: REJECTED %r (failed regex pattern)", phone)
    return None


def validate_email(email: str | None) -> str | None:
    if not email:
        logger.debug("validate_email: input is empty — skipping")
        return None
    email = email.strip().lower()

    if not _EMAIL_RE.match(email):
        logger.debug("validate_email: REJECTED %r (failed email regex)", email)
        return None

    if len(email) > 254:
        logger.debug("validate_email: REJECTED %r (exceeds 254 chars)", email)
        return None

    domain = email.split("@", 1)[-1]

    # Reject image/binary file extensions masquerading as TLDs.
    # Example: "artboard-1dx@0.5x.png" matches the email regex but ".png" is not a TLD.
    tld = domain.rsplit(".", 1)[-1] if "." in domain else ""
    if tld in _EMAIL_BLOCKED_TLDS:
        logger.debug("validate_email: REJECTED %r (TLD %r is a file extension, not a mail TLD)", email, tld)
        return None

    if domain in _EMAIL_JUNK_DOMAINS or any(
        domain == jd or domain.endswith("." + jd) for jd in _EMAIL_JUNK_DOMAINS
    ):
        logger.debug("validate_email: REJECTED %r (junk domain: %s)", email, domain)
        return None

    logger.debug("validate_email: ACCEPTED %r", email)
    return email


def validate_url(url: str | None, *, reject_social: bool = False) -> str | None:
    """
    Validate and normalise a URL.

    Args:
        url: Raw URL string (may be missing scheme).
        reject_social: If True, reject URLs whose domain is a social media platform.
                       Use this when validating the business *website* field so that
                       social media profile URLs are not stored there.
    """
    if not url:
        logger.debug("validate_url: input is empty — skipping")
        return None
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        if not (parsed.scheme in ("http", "https") and parsed.netloc):
            logger.debug("validate_url: REJECTED %r (missing scheme or netloc)", url)
            return None

        if reject_social:
            # Strip leading "www." for comparison
            netloc = parsed.netloc.lower().lstrip("www.")
            if any(netloc == d or netloc.endswith("." + d) for d in _SOCIAL_MEDIA_DOMAINS):
                logger.debug(
                    "validate_url: REJECTED %r (social media URL — store in social_media field instead)",
                    url,
                )
                return None

        logger.debug("validate_url: ACCEPTED %r", url)
        return url
    except Exception as e:
        logger.debug("validate_url: REJECTED %r (parse error: %s)", url, e)
        return None


def validate_rating(rating: float | None) -> float | None:
    if rating is None:
        logger.debug("validate_rating: input is None")
        return None
    if 0.0 <= rating <= 5.0:
        rounded = round(rating, 1)
        logger.debug("validate_rating: ACCEPTED %.1f", rounded)
        return rounded
    logger.debug("validate_rating: REJECTED %.2f (out of [0, 5] range)", rating)
    return None


def validate_coordinates(
    lat: float | None, lng: float | None
) -> tuple[float | None, float | None]:
    if lat is None or lng is None:
        logger.debug("validate_coordinates: one or both values are None (%s, %s)", lat, lng)
        return None, None
    if -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0:
        logger.debug("validate_coordinates: ACCEPTED (%.6f, %.6f)", lat, lng)
        return lat, lng
    logger.debug(
        "validate_coordinates: REJECTED (%.6f, %.6f) — out of valid range", lat, lng
    )
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

def parse_rating_text(text: str | None) -> float | None:
    if not text:
        logger.debug("parse_rating_text: empty input")
        return None
    try:
        cleaned = text.strip().replace(",", ".")
        match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
        if match:
            value = float(match.group(1))
            result = validate_rating(value)
            if result is None:
                logger.debug(
                    "parse_rating_text: parsed %.2f from %r but validation rejected it",
                    value, text,
                )
            return result
    except (ValueError, AttributeError) as e:
        logger.debug("parse_rating_text: could not parse %r — %s", text, e)
    return None


def parse_review_count(text: str | None) -> int | None:
    if not text:
        logger.debug("parse_review_count: empty input")
        return None

    # Strategy A: "1,099 reviews" or "1099 reviews" anywhere in the text.
    # This handles aria-labels like "4.7 stars, 1,099 reviews" correctly —
    # stripping all non-digits from that would give "471099" (wrong).
    m = re.search(r"([\d,]+)\s+reviews?", text, re.IGNORECASE)
    if m:
        try:
            count = int(m.group(1).replace(",", ""))
            logger.debug("parse_review_count: parsed %d via 'N reviews' pattern from %r", count, text)
            return count
        except ValueError as e:
            logger.debug("parse_review_count: int() failed on %r — %s", m.group(1), e)

    # Strategy B: text is a simple count like "(1,099)" or "1099".
    # Guard: skip if the text contains a decimal point (indicates a rating like "4.7",
    # not a review count), or if it contains letters that hint at a mixed description.
    if len(text) <= 20 and "." not in text and not re.search(r"[a-zA-Z]", text):
        digits = re.sub(r"[^\d]", "", text)
        if digits:
            try:
                count = int(digits)
                logger.debug("parse_review_count: parsed %d (digit-strip) from %r", count, text)
                return count
            except ValueError as e:
                logger.debug("parse_review_count: int() failed on %r — %s", digits, e)

    logger.debug("parse_review_count: no review count found in %r", text)
    return None


def decode_cloudflare_email(cfemail: str) -> str | None:
    """Decode a Cloudflare hex-encoded email string (from data-cfemail attribute)."""
    try:
        if not cfemail or len(cfemail) < 4:
            return None
        r = int(cfemail[:2], 16)
        email = "".join(
            chr(int(cfemail[i:i + 2], 16) ^ r)
            for i in range(2, len(cfemail), 2)
        )
        return validate_email(email)
    except Exception as e:
        logger.debug("decode_cloudflare_email: failed for %r — %s", cfemail, e)
        return None


def find_emails_in_text(text: str) -> list[str]:
    """Scan arbitrary text and return all validated emails found, decoding Cloudflare & HTML entities."""
    if not text:
        return []

    # 1. Unescape HTML entities (&amp;, &#64;, etc.)
    clean_text = html.unescape(text)

    valid_emails: list[str] = []
    seen: set[str] = set()

    # 2. Check for Cloudflare obfuscated emails (data-cfemail)
    for cf_hex in _CF_EMAIL_RE.findall(text):
        decoded = decode_cloudflare_email(cf_hex)
        if decoded and decoded not in seen:
            seen.add(decoded)
            valid_emails.append(decoded)

    # 3. Scan standard email regex pattern
    raw_matches = _EMAIL_SCAN.findall(clean_text)
    for raw in raw_matches:
        v = validate_email(raw)
        if v and v not in seen:
            seen.add(v)
            valid_emails.append(v)

    # 4. Check for text-obfuscated emails (e.g., info [at] example [dot] com)
    if not valid_emails and (" [at] " in clean_text or " (at) " in clean_text or " AT " in clean_text):
        deobfuscated = _OBFUSCATED_AT_RE.sub("@", clean_text)
        deobfuscated = _OBFUSCATED_DOT_RE.sub(".", deobfuscated)
        for raw in _EMAIL_SCAN.findall(deobfuscated):
            v = validate_email(raw)
            if v and v not in seen:
                seen.add(v)
                valid_emails.append(v)

    if valid_emails:
        logger.debug(
            "find_emails_in_text: found %d valid emails (%d raw candidates)",
            len(valid_emails), len(raw_matches),
        )
    return valid_emails
