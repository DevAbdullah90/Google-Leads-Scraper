import json
import os
import argparse
import pandas as pd
from pathlib import Path

def flatten_json(y):
    out = {}

    def flatten(x, name=''):
        if type(x) is dict:
            for a in x:
                flatten(x[a], name + a + '_')
        elif type(x) is list:
            out[name[:-1]] = str(x) if x else None
        else:
            out[name[:-1]] = x

    flatten(y)
    return out

def is_empty(val):
    """Check if a value is 'empty' (None, NaN, empty string, empty list/dict string)."""
    if pd.isna(val) or val is None:
        return True
    if isinstance(val, str):
        val = val.strip()
        return val == "" or val == "[]" or val == "{}" or val == "None"
    return False

def main():
    parser = argparse.ArgumentParser(description="Flatten and export Google Leads JSON to CSV and XLSX.")
    parser.add_argument("input_file", help="Path to the source JSON file.")
    parser.add_argument("--output-dir", help="Optional directory to save the exported files.")
    
    args = parser.parse_args()
    
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: File {args.input_file} not found.")
        return

    output_dir = Path(args.output_dir) if args.output_dir else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = input_path.stem
    output_base = output_dir / f"{base_name}_exported"

    print(f"Reading {input_path}...")
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    businesses = data.get('businesses', [])
    if not businesses:
        if isinstance(data, list):
            businesses = data
        else:
            print("Error: No 'businesses' list found in JSON.")
            return

    print(f"Found {len(businesses)} leads. Flattening...")
    flattened_data = [flatten_json(b) for b in businesses]
    
    df = pd.DataFrame(flattened_data)

    print("Pruning empty columns...")
    cols_to_drop = []
    for col in df.columns:
        if df[col].apply(is_empty).all():
            cols_to_drop.append(col)
    
    if cols_to_drop:
        print(f"Dropping {len(cols_to_drop)} empty columns...")
        df.drop(columns=cols_to_drop, inplace=True)

    csv_output = f"{output_base}.csv"
    print(f"Exporting to CSV: {csv_output}")
    df.to_csv(csv_output, index=False, encoding='utf-8-sig')

    xlsx_output = f"{output_base}.xlsx"
    print(f"Exporting to XLSX: {xlsx_output}")
    df.to_excel(xlsx_output, index=False, engine='openpyxl')

    print("Done!")

if __name__ == "__main__":
    main()
