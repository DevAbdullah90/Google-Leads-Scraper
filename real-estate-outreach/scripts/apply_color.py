#!/usr/bin/env python3
"""
Apply background color to Google Sheets range.
Usage: python apply_color.py <spreadsheet_id> <sheet_name> <start_row> <end_row> <color>
"""

import sys
import argparse
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

COLORS = {
    "green": {"red": 0.7, "green": 0.9, "blue": 0.7},
    "red": {"red": 0.9, "green": 0.7, "blue": 0.7},
    "yellow": {"red": 0.9, "green": 0.9, "blue": 0.7},
    "blue": {"red": 0.7, "green": 0.7, "blue": 0.9},
    "white": {"red": 1, "green": 1, "blue": 1},
}

def main():
    parser = argparse.ArgumentParser(description="Apply color to Google Sheets range")
    parser.add_argument("spreadsheet_id", help="Google Sheet ID")
    parser.add_argument("sheet_name", help="Sheet name")
    parser.add_argument("start_row", type=int, help="Start row (1-based)")
    parser.add_argument("end_row", type=int, help="End row (1-based)")
    parser.add_argument("color", choices=COLORS.keys(), help="Background color")
    parser.add_argument("--start-col", default="J", help="Start column (default: J)")
    parser.add_argument("--end-col", default="K", help="End column (default: K)")
    parser.add_argument("--creds-file", default="credentials.json", help="Path to credentials file")
    
    args = parser.parse_args()
    
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    if not Path(args.creds_file).exists():
        print(f"Error: Credentials file '{args.creds_file}' not found.")
        sys.exit(1)
    
    creds = Credentials.from_service_account_file(args.creds_file, scopes=scopes)
    client = gspread.authorize(creds)
    
    spreadsheet = client.open_by_key(args.spreadsheet_id)
    
    # Find the worksheet and get its ID
    worksheet = None
    for ws in spreadsheet.worksheets():
        if ws.title == args.sheet_name:
            worksheet = ws
            break
    
    if worksheet is None:
        print(f"Error: Sheet '{args.sheet_name}' not found.")
        sys.exit(1)
    
    sheet_id = worksheet.id
    
    # Convert column letters to indices
    def col_to_index(col):
        result = 0
        for char in col.upper():
            result = result * 26 + (ord(char) - ord('A') + 1)
        return result - 1
    
    start_col_idx = col_to_index(args.start_col)
    end_col_idx = col_to_index(args.end_col) + 1
    
    # Build batch update request
    requests = [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": args.start_row - 1,
                    "endRowIndex": args.end_row,
                    "startColumnIndex": start_col_idx,
                    "endColumnIndex": end_col_idx
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
    
    try:
        spreadsheet.batch_update({"requests": requests})
        print(f"Applied {args.color} background to {args.sheet_name}!{args.start_col}{args.start_row}:{args.end_col}{args.end_row}")
    except Exception as e:
        print(f"Error applying formatting: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
