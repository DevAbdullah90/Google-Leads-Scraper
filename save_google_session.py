"""
Run this script ONCE to log into Google in a real browser window.
Your session cookies are saved to data/google_session.json and reused
by the scraper automatically on every future run.

Usage:
    venv/Scripts/python.exe save_google_session.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from playwright.async_api import async_playwright

SESSION_FILE = Path(__file__).parent / "data" / "google_session.json"


async def main() -> None:
    async with async_playwright() as p:
        print("Opening Chrome — please sign into Google, then close the browser window.")
        print(f"Session will be saved to: {SESSION_FILE}\n")

        browser = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = await context.new_page()

        # Open Google Maps directly — signing in here is enough for Maps scraping
        await page.goto("https://www.google.com/maps", wait_until="domcontentloaded")

        print("Sign in with your Google account in the browser window.")
        print("When you are fully signed in and can see Google Maps, press Enter here.")
        input("Press Enter to save the session and close the browser...")

        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(SESSION_FILE))
        print(f"\nSession saved to {SESSION_FILE}")
        print("You can now run the scraper normally — it will use this session.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
