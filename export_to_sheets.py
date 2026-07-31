import os
import sys
import json
import argparse
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

def get_latest_json_file(output_dir):
    """Find the most recently modified JSON file in the output directory."""
    path = Path(output_dir)
    if not path.exists():
        return None
    json_files = list(path.glob("*.json"))
    if not json_files:
        return None
    # Sort by modification time, newest first
    json_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return json_files[0]

def main():
    parser = argparse.ArgumentParser(description="Upload scraped leads from JSON to Google Sheets.")
    parser.add_argument("input_file", nargs="?", help="Path to the scraped leads JSON file (defaults to the latest file in output/)")
    parser.add_argument("--spreadsheet-id", default="1-pNAcHLkZtERS3KZqSt9l-wPb0QIXdXDgSdCtmSAnGk", help="Google Sheet ID")
    parser.add_argument("--creds-file", default="credentials.json", help="Path to Google Service Account credentials JSON")
    
    args = parser.parse_args()
    
    # 1. Determine JSON file to upload
    if args.input_file:
        json_path = Path(args.input_file)
    else:
        json_path = get_latest_json_file("output")
        if not json_path:
            print("Error: No JSON files found in 'output/' directory. Please specify the file path manually.")
            sys.exit(1)
            
    if not json_path.exists():
        print(f"Error: File '{json_path}' not found.")
        sys.exit(1)
        
    print(f"Reading leads from: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    businesses = data.get("businesses", [])
    if not businesses:
        if isinstance(data, list):
            businesses = data
        else:
            print("Error: No business leads found in the JSON file.")
            sys.exit(1)
            
    print(f"Found {len(businesses)} leads to upload.")
    
    # 2. Extract and format rows
    headers = [
        "Business Name", 
        "Phone", 
        "Email", 
        "Website", 
        "Category", 
        "Rating", 
        "Reviews", 
        "Full Address", 
        "Google Maps URL"
    ]
    
    rows = []
    for b in businesses:
        contact = b.get("contact", {})
        ratings = b.get("ratings", {})
        address = b.get("address", {})
        business_info = b.get("business_info", {})
        
        phone_val = contact.get("phone", "") or ""
        if phone_val.startswith("+") or phone_val.startswith("-") or phone_val.startswith("="):
            phone_val = f"'{phone_val}"
            
        row = [
            b.get("business_name", ""),
            phone_val,
            contact.get("email", "") or "",
            contact.get("website", "") or "",
            business_info.get("category", "") or "",
            ratings.get("average_rating", "") or "",
            ratings.get("total_reviews", "") or "",
            address.get("full_address", "") or "",
            b.get("google_maps_url", "")
        ]
        rows.append(row)
        
    # 3. Authenticate and connect to Google Sheets
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    if not os.path.exists(args.creds_file):
        print(f"Error: Credentials file '{args.creds_file}' not found.")
        sys.exit(1)
        
    try:
        print("Authenticating with Google Sheets API...")
        creds = Credentials.from_service_account_file(args.creds_file, scopes=scopes)
        client = gspread.authorize(creds)
        
        print(f"Opening Spreadsheet ID: {args.spreadsheet_id}")
        spreadsheet = client.open_by_key(args.spreadsheet_id)
        
        # Get or create worksheet
        worksheet_title = "Scraped Leads"
        try:
            worksheet = spreadsheet.worksheet(worksheet_title)
            print(f"Found existing worksheet '{worksheet_title}'.")
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=worksheet_title, rows=1000, cols=10)
            print(f"Created new worksheet '{worksheet_title}'.")
            # Write headers only for new worksheet
            print("Writing headers...")
            worksheet.append_row(headers)
            
        # Check existing data in worksheet for deduplication
        existing_data = worksheet.get_all_values()
        if len(existing_data) <= 1:
            print("Writing headers...")
            worksheet.append_row(headers)
            existing_data = [headers]

        # Build lookup sets for fast O(1) deduplication (Phone & Google Maps URL)
        existing_phones: set[str] = set()
        existing_urls: set[str] = set()

        for r in existing_data[1:]:
            if len(r) > 1 and r[1]:
                p = r[1].lstrip("'").strip()
                if p:
                    existing_phones.add(p)
            if len(r) > 8 and r[8]:
                u = r[8].strip()
                if u:
                    existing_urls.add(u)

        # Filter rows to only append new unique leads
        new_rows = []
        skipped_count = 0
        for r in rows:
            p_val = r[1].lstrip("'").strip()
            u_val = r[8].strip()

            is_dup = False
            if p_val and p_val in existing_phones:
                is_dup = True
            elif u_val and u_val in existing_urls:
                is_dup = True

            if is_dup:
                skipped_count += 1
            else:
                new_rows.append(r)
                if p_val:
                    existing_phones.add(p_val)
                if u_val:
                    existing_urls.add(u_val)

        if skipped_count > 0:
            print(f"[Deduplication] Skipped {skipped_count} lead(s) already present in Google Sheet.")

        if not new_rows:
            print("All leads in this file already exist in your Google Sheet! No new rows appended.")
            return

        print(f"Appending {len(new_rows)} new unique lead(s) to the sheet...")
        worksheet.append_rows(new_rows, value_input_option="USER_ENTERED")
        
        print(f"Success! View your Google Sheet at: https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}")
        
    except gspread.exceptions.APIError as e:
        print("\nGoogle Sheets API Error:")
        print(e)
        # Check for permission denied
        if "PERMISSION_DENIED" in str(e):
            # Try to get client email
            with open(args.creds_file, "r") as f:
                creds_data = json.load(f)
            client_email = creds_data.get("client_email", "the service account email")
            print(f"\n[IMPORTANT] Access Denied. Make sure you have shared your Google Sheet with the Service Account email address:")
            print(f"👉  {client_email}  👈")
            print("Set its role to 'Editor'.")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred during upload: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
