#!/usr/bin/env python3
"""
Script to apply formatting to Google Sheets.
Usage: python format_sheet.py <spreadsheet_id> <range> <color>
Example: python format_sheet.py 1-pNAcHLkZtERS3KZqSt9l-wPb0QIXdXDgSdCtmSAnGk "Scraped Leads!J2:K11" green
"""

import sys
import json
import argparse
from pathlib import Path
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

COLORS = {
    "green": {"red": 0.7, "green": 0.9, "blue": 0.7},
    "red": {"red": 0.9, "green": 0.7, "blue": 0.7},
    "yellow": {"red": 0.9, "green": 0.9, "blue": 0.7},
    "blue": {"red": 0.7, "green": 0.7, "blue": 0.9},
    "white": {"red": 1, "green": 1, "blue": 1},
}

def main():
    parser = argparse.ArgumentParser(description="Apply color formatting to Google Sheets range")
    parser.add_argument("spreadsheet_id", help="Google Sheet ID")
    parser.add_argument("range", help="Range to format (e.g., 'Scraped Leads!J2:K11')")
    parser.add_argument("color", choices=COLORS.keys(), help="Background color")
    parser.add_argument("--creds-file", default="credentials.json", help="Path to credentials file")
    
    args = parser.parse_args()
    
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    
    if not Path(args.creds_file).exists():
        print(f"Error: Credentials file '{args.creds_file}' not found.")
        sys.exit(1)
    
    creds = Credentials.from_service_account_file(args.creds_file, scopes=scopes)
    service = build("sheets", "v4", credentials=creds)
    
    body = {
        "requests": [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": get_sheet_id(service, args.spreadsheet_id, args.range),
                        "startRowIndex": get_row_index(args.range, "start"),
                        "endRowIndex": get_row_index(args.range, "end"),
                        "startColumnIndex": get_col_index(args.range, "start"),
                        "endColumnIndex": get_col_index(args.range, "end"),
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": COLORS[args.color]
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor"
                }
            }
        ]
    }
    
    result = service.spreadsheets().batchUpdate(
        spreadsheetId=args.spreadsheet_id,
        body=body
    ).execute()
    
    print(f"Applied {args.color} background to {args.range}")
    print(f"Updated {result.get('totalUpdates', 0)} cells")

def get_sheet_id(service, spreadsheet_id, range_str):
    """Extract sheet ID from range string."""
    sheet_name = range_str.split("!")[0]
    spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in spreadsheet.get("sheets", []):
        if sheet["properties"]["title"] == sheet_name:
            return sheet["properties"]["sheetId"]
    return 0

def get_row_index(range_str, position):
    """Extract row index from range string like 'A1:B10'."""
    import re
    range_part = range_str.split("!")[1] if "!" in range_str else range_str
    match = re.findall(r'(\d+)', range_part)
    if len(match) >= 2:
        start_row = int(match[0]) - 1
        end_row = int(match[1])
        return start_row if position == "start" else end_row
    return 0

def get_col_index(range_str, position):
    """Extract column index from range string like 'A1:B10'."""
    import re
    range_part = range_str.split("!")[1] if "!" in range_str else range_str
    match = re.findall(r'([A-Z]+)', range_part)
    if len(match) >= 2:
        start_col = letter_to_column(match[0])
        end_col = letter_to_column(match[1]) + 1
        return start_col if position == "start" else end_col
    return 0

def letter_to_column(letter):
    """Convert column letter to 0-based index."""
    result = 0
    for char in letter.upper():
        result = result * 26 + (ord(char) - ord('A') + 1)
    return result - 1

if __name__ == "__main__":
    main()
