#!/usr/bin/env python3
"""
Mark leads as SENT in Google Sheets with green background.
Usage: python mark_sent.py <spreadsheet_id> <start_row> <end_row>
"""

import sys
import json
import argparse
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

def main():
    parser = argparse.ArgumentParser(description="Mark leads as SENT with green background")
    parser.add_argument("spreadsheet_id", help="Google Sheet ID")
    parser.add_argument("start_row", type=int, help="Starting row number (1-based)")
    parser.add_argument("end_row", type=int, help="Ending row number (1-based)")
    parser.add_argument("--sheet", default="Scraped Leads", help="Sheet name")
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
    worksheet = spreadsheet.worksheet(args.sheet)
    
    # Update Status and Sent Date columns (J and K)
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    
    for row_num in range(args.start_row, args.end_row + 1):
        # Column J (10) = Status, Column K (11) = Sent Date
        worksheet.update_cell(row_num, 10, "SENT")
        worksheet.update_cell(row_num, 11, today)
        print(f"Row {row_num}: Marked as SENT")
    
    # Apply green background using batch update
    # Get sheet ID
    sheet_id = None
    for sheet in spreadsheet.sheet1._properties if hasattr(spreadsheet, 'sheet1') else []:
        if sheet.get("title") == args.sheet:
            sheet_id = sheet.get("sheetId")
            break
    
    # If we can't get sheet ID, try alternative method
    if sheet_id is None:
        spreadsheet_data = client.open_by_key(args.spreadsheet_id)
        for sheet in spreadsheet_data.worksheets():
            if sheet.title == args.sheet:
                sheet_id = sheet.id
                break
    
    if sheet_id is not None:
        # Build batch update request for formatting
        green_color = {"red": 0.7, "green": 0.9, "blue": 0.7}
        
        requests = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": args.start_row - 1,
                        "endRowIndex": args.end_row,
                        "startColumnIndex": 9,  # Column J (0-based)
                        "endColumnIndex": 11    # Column K (0-based, exclusive)
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": green_color
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor"
                }
            }
        ]
        
        try:
            spreadsheet.batch_update({"requests": requests})
            print(f"Applied green background to rows {args.start_row}-{args.end_row}")
        except Exception as e:
            print(f"Warning: Could not apply formatting: {e}")
            print("Status values were still updated successfully.")
    
    print(f"\nDone! Marked {args.end_row - args.start_row + 1} leads as SENT.")

if __name__ == "__main__":
    main()
