"""
Google Sheets Sync module for pre-scrape skipping.

Loads existing business URLs and Phone numbers from Google Sheets to enable
instant O(1) deduplication during Google Maps scrolling.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

from config.settings import BASE_DIR, GOOGLE_SHEETS_SPREADSHEET_ID

logger = logging.getLogger(__name__)

def fetch_sheet_existing_urls(
    spreadsheet_id: str = GOOGLE_SHEETS_SPREADSHEET_ID,
    creds_file: str | Path | None = None,
) -> set[str]:
    """
    Fetch all existing Google Maps URLs and Phone numbers from the Google Sheet.

    Returns a normalized set of strings (URLs and cleaned phone numbers)
    for O(1) in-memory lookups during Google Maps scrolling.
    """
    if creds_file is None:
        creds_file = BASE_DIR / "credentials.json"
    else:
        creds_file = Path(creds_file)

    if not creds_file.exists():
        logger.warning("[sheets_sync] Credentials file %s not found — pre-scrape sheet skip disabled", creds_file)
        return set()

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    try:
        creds = Credentials.from_service_account_file(str(creds_file), scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(spreadsheet_id)

        try:
            worksheet = spreadsheet.worksheet("Scraped Leads")
        except gspread.exceptions.WorksheetNotFound:
            # Fall back to first sheet
            worksheet = spreadsheet.get_worksheet(0)

        existing_rows = worksheet.get_all_values()
        if len(existing_rows) <= 1:
            logger.debug("[sheets_sync] Sheet has no lead data yet")
            return set()

        existing_identifiers: set[str] = set()

        for r in existing_rows[1:]:
            # Index 1 = Phone
            if len(r) > 1 and r[1]:
                phone = r[1].lstrip("'").strip()
                if phone:
                    existing_identifiers.add(phone)
            # Index 8 = Google Maps URL
            if len(r) > 8 and r[8]:
                url = r[8].strip()
                if url:
                    existing_identifiers.add(url)
                    # Also extract hex place ID from URL if present
                    m = re.search(r"(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)", url)
                    if m:
                        existing_identifiers.add(m.group(1))

        logger.info(
            "[sheets_sync] Loaded %d existing identifiers (URLs/Phones/PlaceIDs) from Google Sheet ✓",
            len(existing_identifiers),
        )
        return existing_identifiers

    except Exception as e:
        logger.warning("[sheets_sync] Failed to fetch Google Sheet history: %s — skipping disabled", e)
        return set()
