"""
Master Google Sheet Deduplication Script (clean_sheet.py)

Connects to your Master Google Sheet, scans all rows, removes duplicate leads
(based on Phone number & Google Maps URL), and preserves outreach status (SENT/FAILED).
"""

import os
import sys
import json
import argparse
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import GOOGLE_SHEETS_SPREADSHEET_ID

INVALID_KEYS = {"", "—", "-", "n/a", "none", "null", "undefined", "'—", "'-", "'"}

def is_valid_key(val: str) -> bool:
    """Return True if val is a valid non-empty identifier key."""
    if not val:
        return False
    clean_v = str(val).lstrip("'").strip().lower()
    return clean_v not in INVALID_KEYS and len(clean_v) > 2

def clean_phone(phone_str: str) -> str:
    """Normalize phone number for clean matching."""
    if not phone_str:
        return ""
    cleaned = phone_str.lstrip("'").strip()
    return cleaned if is_valid_key(cleaned) else ""

def is_sent_status(row: list[str]) -> bool:
    """Check if row has an active outreach status (e.g., SENT / EMAIL SENT)."""
    for val in row:
        val_upper = str(val).upper().strip()
        if "SENT" in val_upper or "SUCCESS" in val_upper:
            return True
    return False

def main():
    parser = argparse.ArgumentParser(description="Clean duplicate leads from Master Google Sheet.")
    parser.add_argument(
        "--spreadsheet-id",
        default=GOOGLE_SHEETS_SPREADSHEET_ID,
        help="Master Google Sheet ID"
    )
    parser.add_argument(
        "--creds-file",
        default=str(BASE_DIR / "credentials.json"),
        help="Path to Google Service Account credentials JSON"
    )
    parser.add_argument(
        "--worksheet",
        default="Scraped Leads",
        help="Worksheet name to clean"
    )

    args = parser.parse_args()

    creds_path = Path(args.creds_file)
    if not creds_path.exists():
        print(f"Error: Credentials file '{creds_path}' not found.")
        sys.exit(1)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    try:
        print("Authenticating with Google Sheets API...")
        creds = Credentials.from_service_account_file(str(creds_path), scopes=scopes)
        client = gspread.authorize(creds)

        print(f"Opening Master Spreadsheet ID: {args.spreadsheet_id}")
        spreadsheet = client.open_by_key(args.spreadsheet_id)

        try:
            worksheet = spreadsheet.worksheet(args.worksheet)
            print(f"Connected to worksheet '{args.worksheet}'.")
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.get_worksheet(0)
            print(f"Worksheet '{args.worksheet}' not found — using first worksheet '{worksheet.title}'.")

        all_rows = worksheet.get_all_values()
        if not all_rows or len(all_rows) <= 1:
            print("Sheet has no data rows to clean!")
            return

        header = all_rows[0]
        data_rows = all_rows[1:]
        total_input_rows = len(data_rows)
        print(f"Analyzing {total_input_rows} total lead rows in Google Sheet...")

        # Track seen Phone numbers, Google Maps URLs, and Business Names
        seen_phones: set[str] = set()
        seen_urls: set[str] = set()
        seen_names: set[str] = set()
        unique_rows: list[list[str]] = []
        duplicate_count = 0

        for r in data_rows:
            name_val = r[0].strip() if len(r) > 0 else ""
            phone_val = clean_phone(r[1]) if len(r) > 1 else ""
            url_val = r[8].strip() if len(r) > 8 else ""

            is_dup = False

            if is_valid_key(url_val) and url_val in seen_urls:
                is_dup = True
            elif is_valid_key(phone_val) and phone_val in seen_phones:
                is_dup = True
            elif (not is_valid_key(phone_val) and not is_valid_key(url_val)) and is_valid_key(name_val) and name_val in seen_names:
                is_dup = True

            if is_dup:
                # If this duplicate happens to have a SENT status while the previous didn't,
                # replace the un-sent entry with this sent entry
                if is_sent_status(r):
                    for idx, ex in enumerate(unique_rows):
                        ex_name = ex[0].strip() if len(ex) > 0 else ""
                        ex_p = clean_phone(ex[1]) if len(ex) > 1 else ""
                        ex_u = ex[8].strip() if len(ex) > 8 else ""
                        if (is_valid_key(url_val) and ex_u == url_val) or \
                           (is_valid_key(phone_val) and ex_p == phone_val) or \
                           (is_valid_key(name_val) and ex_name == name_val):
                            unique_rows[idx] = r
                            break
                duplicate_count += 1
            else:
                unique_rows.append(r)
                if is_valid_key(phone_val):
                    seen_phones.add(phone_val)
                if is_valid_key(url_val):
                    seen_urls.add(url_val)
                if is_valid_key(name_val):
                    seen_names.add(name_val)

        if duplicate_count == 0:
            print("Sheet is 100% clean! No duplicate rows were found.")
            return

        print(f"\n[Deduplication Summary]")
        print(f"  - Total input rows  : {total_input_rows}")
        print(f"  - Duplicates removed: {duplicate_count}")
        print(f"  - Unique leads kept : {len(unique_rows)}")

        # Overwrite worksheet with cleaned rows
        print("\nUpdating Google Sheet with cleaned rows...")
        final_table = [header] + unique_rows
        
        # Clear existing worksheet and write deduplicated table
        worksheet.clear()
        worksheet.update(range_name="A1", values=final_table, value_input_option="USER_ENTERED")

        print(f"Success! Master Google Sheet deduplicated and updated.")
        print(f"View your Google Sheet: https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}")

    except Exception as e:
        print(f"\nError cleaning Google Sheet: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
