"""
Playwright browser lifecycle management with stealth and anti-detection.

Logs cover:
 - Browser/context creation parameters (UA, viewport, proxy)
 - Every consent button selector tried and the result
 - CAPTCHA detection with the matching selector
 - Browser restart events
"""

from __future__ import annotations

import logging
import random
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from config.selectors import CAPTCHA_SELECTORS, CONSENT_BUTTON_SELECTORS
from config.settings import (
    GOOGLE_SESSION_FILE,
    HEADLESS,
    PAGE_LOAD_TIMEOUT,
    PROXIES_FILE,
    VIEWPORT_HEIGHT_RANGE,
    VIEWPORT_WIDTH_RANGE,
)
from scraper.utils import log_subsection, parse_proxy, random_user_agent

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Built-in stealth (replaces playwright-stealth library)
# ─────────────────────────────────────────────────────────────────────────────

_STEALTH_JS = """
() => {
    // Hide webdriver flag
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

    // Spoof plugins (empty plugins = headless browser giveaway)
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const arr = [
                {name:'Chrome PDF Plugin', filename:'internal-pdf-viewer', description:'Portable Document Format'},
                {name:'Chrome PDF Viewer', filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai', description:''},
            ];
            arr.__proto__ = PluginArray.prototype;
            return arr;
        }
    });

    // Spoof languages
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});

    // Add chrome runtime object (absent in headless)
    if (!window.chrome) {
        window.chrome = {
            runtime: {
                PlatformOs: {MAC:'mac',WIN:'win',ANDROID:'android',CROS:'cros',LINUX:'linux',OPENBSD:'openbsd'},
                PlatformArch: {ARM:'arm',ARM64:'arm64',X86_32:'x86-32',X86_64:'x86-64',MIPS:'mips',MIPS64:'mips64'},
                PlatformNaclArch: {ARM:'arm',X86_32:'x86-32',X86_64:'x86-64',MIPS:'mips',MIPS64:'mips64'},
                RequestUpdateCheckStatus: {THROTTLED:'throttled',NO_UPDATE:'no_update',UPDATE_AVAILABLE:'update_available'},
                OnInstalledReason: {INSTALL:'install',UPDATE:'update',CHROME_UPDATE:'chrome_update',SHARED_MODULE_UPDATE:'shared_module_update'},
                OnRestartRequiredReason: {APP_UPDATE:'app_update',OS_UPDATE:'os_update',PERIODIC:'periodic'},
            }
        };
    }

    // Spoof permissions query (headless returns 'denied' for notifications)
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : originalQuery(parameters);

    // Spoof hardware properties (headless defaults reveal automation)
    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
    Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

    // Remove CDP / automation artifacts
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
}
"""


async def apply_stealth(page: Page) -> None:
    """
    Inject anti-detection patches into the page before any navigation.
    Replaces the playwright-stealth library with equivalent inline JavaScript.
    """
    await page.add_init_script(_STEALTH_JS)
    logger.debug("  Stealth patches applied (navigator.webdriver, plugins, chrome runtime, permissions)")


# ─────────────────────────────────────────────────────────────────────────────
# Browser factory
# ─────────────────────────────────────────────────────────────────────────────

async def launch_browser(
    playwright: Playwright,
    *,
    headless: bool = HEADLESS,
    proxy: str | None = None,
    proxy_file: str | None = None,
) -> tuple[Browser, BrowserContext, Page]:
    """
    Launch Chromium with stealth settings.

    Returns (browser, context, page) — caller is responsible for closing.
    """
    proxy_config = _resolve_proxy(proxy, proxy_file)
    ua = random_user_agent()
    width  = random.randint(*VIEWPORT_WIDTH_RANGE)
    height = random.randint(*VIEWPORT_HEIGHT_RANGE)

    logger.info(
        "Launching browser | headless=%s | viewport=%dx%d | proxy=%s",
        headless, width, height,
        proxy_config["server"] if proxy_config else "none",
    )
    logger.debug("  User-Agent: %s", ua)

    browser = await playwright.chromium.launch(
        headless=headless,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-extensions",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            f"--window-size={width},{height}",
        ],
    )
    logger.debug("  Chromium process started (PID managed by Playwright)")

    context_kwargs: dict = dict(
        viewport={"width": width, "height": height},
        user_agent=ua,
        locale="en-US",
        timezone_id="America/New_York",
        java_script_enabled=True,
        accept_downloads=False,
        ignore_https_errors=bool(proxy_config),
    )
    if proxy_config:
        context_kwargs["proxy"] = proxy_config
        logger.debug("  Proxy applied: %s", proxy_config["server"])

    # Load saved Google session cookies if available (bypasses limited-view bot detection)
    if GOOGLE_SESSION_FILE.exists():
        context_kwargs["storage_state"] = str(GOOGLE_SESSION_FILE)
        logger.info("  Google session loaded from %s", GOOGLE_SESSION_FILE)
    else:
        logger.debug(
            "  No Google session file found at %s — running without cookies "
            "(run save_google_session.py once to enable full page access)",
            GOOGLE_SESSION_FILE,
        )

    context = await browser.new_context(**context_kwargs)
    context.set_default_timeout(PAGE_LOAD_TIMEOUT)
    context.set_default_navigation_timeout(PAGE_LOAD_TIMEOUT)

    await context.set_extra_http_headers({
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    })
    logger.debug("  Extra HTTP headers set (Accept-Language, Accept-Encoding, Accept)")

    page = await context.new_page()
    await apply_stealth(page)
    logger.debug("  playwright-stealth applied to page")

    logger.info("Browser ready ✓")
    return browser, context, page


async def close_browser(browser: Browser, context: BrowserContext) -> None:
    """Safely close context and browser, ignoring errors."""
    logger.debug("Closing browser context…")
    for obj in (context, browser):
        try:
            await obj.close()
        except Exception as e:
            logger.debug("  Ignore close error: %s", e)
    logger.debug("Browser closed.")


# ─────────────────────────────────────────────────────────────────────────────
# Popup / consent handling
# ─────────────────────────────────────────────────────────────────────────────

async def dismiss_consent(page: Page) -> bool:
    """
    Click through Google consent dialogs if present.

    Tries each known selector in order and logs every attempt.
    Returns True if a button was clicked.
    """
    logger.debug("Checking for consent popup (%d known selectors)…", len(CONSENT_BUTTON_SELECTORS))

    for selector in CONSENT_BUTTON_SELECTORS:
        try:
            btn = await page.query_selector(selector)
            if btn and await btn.is_visible():
                logger.info("  Consent popup found via %r — clicking…", selector)
                await btn.click()
                try:
                    await page.wait_for_load_state("networkidle", timeout=5_000)
                except Exception:
                    pass  # networkidle may never fire on Maps; that's fine
                logger.info("  Consent dismissed ✓")
                return True
            elif btn:
                logger.debug("  %r matched but element is not visible — skipping", selector)
            else:
                logger.debug("  %r → no element found", selector)
        except Exception as e:
            logger.debug("  %r → error: %s", selector, e)

    logger.debug("No consent popup detected (or already accepted).")
    return False


async def check_captcha(page: Page) -> bool:
    """
    Return True if a CAPTCHA is visible on the current page.
    Logs the matching selector so you know exactly which indicator triggered.
    """
    logger.debug("Checking for CAPTCHA (%d selectors)…", len(CAPTCHA_SELECTORS))

    for selector in CAPTCHA_SELECTORS:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                logger.error(
                    "⚠ CAPTCHA DETECTED via selector %r on URL: %s", selector, page.url
                )
                logger.error(
                    "  Action required: solve manually or add more delays/proxies."
                )
                return True
        except Exception as e:
            logger.debug("  CAPTCHA selector %r error: %s", selector, e)

    logger.debug("No CAPTCHA detected.")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Context manager wrapper
# ─────────────────────────────────────────────────────────────────────────────

class BrowserSession:
    """
    Async context manager that owns a full Playwright → Browser → Context → Page stack.

    async with BrowserSession(headless=True) as session:
        await session.page.goto(url)
    """

    def __init__(
        self,
        *,
        headless: bool = HEADLESS,
        proxy: str | None = None,
        proxy_file: str | None = None,
    ) -> None:
        self.headless = headless
        self.proxy = proxy
        self.proxy_file = proxy_file

        self._playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def __aenter__(self) -> "BrowserSession":
        logger.debug("BrowserSession.__aenter__ — starting Playwright…")
        self._playwright = await async_playwright().start()
        self.browser, self.context, self.page = await launch_browser(
            self._playwright,
            headless=self.headless,
            proxy=self.proxy,
            proxy_file=self.proxy_file,
        )
        return self

    async def __aexit__(self, *_) -> None:
        logger.debug("BrowserSession.__aexit__ — shutting down…")
        if self.browser and self.context:
            await close_browser(self.browser, self.context)
        if self._playwright:
            await self._playwright.stop()
            logger.debug("Playwright stopped.")

    async def new_page(self) -> Page:
        """Open a fresh stealth page in the same context."""
        assert self.context is not None
        page = await self.context.new_page()
        await apply_stealth(page)
        logger.debug("New page opened in existing context.")
        return page

    async def restart(self) -> None:
        """
        Close and reopen the entire browser.
        Called periodically to prevent memory leaks and detection fingerprinting.
        """
        logger.info("━━ Browser restart triggered ━━")
        if self.browser and self.context:
            await close_browser(self.browser, self.context)
        assert self._playwright is not None
        self.browser, self.context, self.page = await launch_browser(
            self._playwright,
            headless=self.headless,
            proxy=self.proxy,
            proxy_file=self.proxy_file,
        )
        logger.info("Browser restarted successfully ✓")


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_proxy(proxy: str | None, proxy_file: str | None) -> dict | None:
    if proxy:
        logger.debug("Using explicit proxy argument.")
        return parse_proxy(proxy)
    if proxy_file:
        logger.debug("Loading proxy from file: %s", proxy_file)
        return _random_proxy_from_file(proxy_file)
    if PROXIES_FILE.exists() and PROXIES_FILE.stat().st_size > 0:
        logger.debug("Proxy file found at default location (%s) — loading.", PROXIES_FILE)
        return _random_proxy_from_file(str(PROXIES_FILE))
    logger.debug("No proxy configured — running direct.")
    return None


def _random_proxy_from_file(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            lines = [l.strip() for l in fh if l.strip() and not l.startswith("#")]
        if lines:
            chosen = random.choice(lines)
            logger.debug("Selected proxy from %d entries in %s", len(lines), path)
            return parse_proxy(chosen)
        else:
            logger.warning("Proxy file %s is empty (no non-comment lines).", path)
    except Exception as e:
        logger.warning("Could not load proxies from %s: %s", path, e)
    return None
