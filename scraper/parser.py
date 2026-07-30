"""
Low-level Playwright element-querying helpers.

All functions are null-safe (return None instead of raising).

Logging philosophy:
 - Successful selector hits → DEBUG (which selector worked)
 - Failed selectors         → not logged individually (too noisy; callers log the field summary)
"""

from __future__ import annotations

import logging
from typing import Optional

from playwright.async_api import ElementHandle, Page

from scraper.utils import clean_text

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Single-element helpers
# ─────────────────────────────────────────────────────────────────────────────

async def get_text(element: ElementHandle | None) -> str | None:
    """Return inner_text of an element, or None on any failure."""
    if element is None:
        return None
    try:
        return clean_text(await element.inner_text())
    except Exception as e:
        logger.debug("get_text failed: %s", e)
        return None


async def get_attr(element: ElementHandle | None, attr: str) -> str | None:
    """Return an attribute value of an element, or None on any failure."""
    if element is None:
        return None
    try:
        value = await element.get_attribute(attr)
        return value.strip() if value else None
    except Exception as e:
        logger.debug("get_attr(%r) failed: %s", attr, e)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Multi-selector helpers — try a list, return first that works
# ─────────────────────────────────────────────────────────────────────────────

async def first_element(page: Page, selectors: list[str]) -> ElementHandle | None:
    """
    Return the first element matched by any selector in the list.
    Logs which selector succeeded at DEBUG level.
    """
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                logger.debug("  first_element: hit via %r", selector)
                return el
        except Exception as e:
            logger.debug("  first_element: selector %r raised %s", selector, e)
    return None


async def first_text(page: Page, selectors: list[str]) -> str | None:
    """
    Return inner_text of the first matched element across a list of selectors.
    Logs the selector that worked and the raw value found.
    """
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                text = await get_text(el)
                if text:
                    logger.debug("  first_text: hit via %r → %r", selector, text[:80])
                    return text
        except Exception as e:
            logger.debug("  first_text: selector %r raised %s", selector, e)
    return None


async def first_attr(page: Page, selectors: list[str], attr: str) -> str | None:
    """
    Return the attribute value from the first matched element.
    Logs the selector and attribute value on success.
    """
    for selector in selectors:
        try:
            el = await page.query_selector(selector)
            if el:
                value = await get_attr(el, attr)
                if value:
                    logger.debug(
                        "  first_attr[%r]: hit via %r → %r", attr, selector, value[:120]
                    )
                    return value
        except Exception as e:
            logger.debug("  first_attr[%r]: selector %r raised %s", attr, selector, e)
    return None


async def all_elements(page: Page, selectors: list[str]) -> list[ElementHandle]:
    """
    Return all elements from the first selector that yields results.
    Logs which selector was used and how many elements were found.
    """
    for selector in selectors:
        try:
            elements = await page.query_selector_all(selector)
            if elements:
                logger.debug(
                    "  all_elements: %d elements via %r", len(elements), selector
                )
                return elements
        except Exception as e:
            logger.debug("  all_elements: selector %r raised %s", selector, e)
    return []


async def all_texts(page: Page, selectors: list[str]) -> list[str]:
    """
    Collect inner_text from all elements matched by the first working selector.
    """
    elements = await all_elements(page, selectors)
    texts: list[str] = []
    for el in elements:
        text = await get_text(el)
        if text:
            texts.append(text)
    if texts:
        logger.debug("  all_texts: collected %d non-empty strings", len(texts))
    return texts
