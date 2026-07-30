# Plan — Simple Lead Export

## Phase 1: Foundation & Data Loading
1. Create `export_leads.py` script.
2. Implement CLI argument parsing using `argparse`.
3. Load JSON data and extract the `businesses` list.

## Phase 2: Flattening & Transformation
1. Implement a robust flattening function (using `pandas.json_normalize` or a custom recursive flattener).
2. Convert the list of businesses into a Pandas DataFrame.
3. Implement the dynamic pruning logic:
   - Identify columns where all values are null/empty.
   - Drop those columns from the DataFrame.

## Phase 3: Export Logic
1. Determine output paths based on input filename and optional output directory.
2. Export DataFrame to CSV using `df.to_csv()`.
3. Export DataFrame to XLSX using `df.to_excel()` with the `openpyxl` engine.

## Phase 4: Validation & Testing
1. Test with the provided `bakery_in_78745_20260505_201317.json` file.
2. Verify that nested fields like `contact.email` become `contact_email`.
3. Verify that columns which are empty across all leads (e.g., `social_media_linkedin` if no leads have it) are missing from the files.
4. Verify files are saved with the `_exported` suffix.
