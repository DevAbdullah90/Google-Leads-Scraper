# Plan: Lead Filtration & Format Conversion

## Group 1: Data Model & Utilities
1.  **Lead Model Alignment:** Ensure the filtering script uses the existing `Business` model or a derivative to validate input JSONL lines.
2.  **Flattening Utility:** Create a function to convert nested JSON objects into a flat dictionary suitable for Pandas/CSV.
3.  **Category Discovery:** Implement an efficient pass to collect all unique categories from a JSONL file to populate whitelists/blacklists.

## Group 2: Core Filtration Logic
1.  **Filter Engine:** Implement a `FilterEngine` class that applies a set of configurable rules (AND/OR logic) to a lead.
2.  **Rule Implementation:**
    - `ContactRule`: Checks for phone/email/website.
    - `QualityRule`: Checks rating/reviews.
    - `CategoryRule`: Handles whitelist/blacklist; supports both ID selection and manual string input.
    - `KeywordRule`: Regex or simple substring search in text fields.
    - `SocialMediaRule`: Checks for specific platforms using user-defined logic (AND/OR).
3.  **Deduplication:** Add an in-memory `Set` to track `place_id` and skip duplicates during the stream.

## Group 3: CLI & User Interface
1.  **CLI Arguments:** Setup `argparse` to handle all filter criteria as optional flags.
2.  **Interactive Prompts:**
    - Use `rich.prompt.Confirm` to ask *which* filters to activate.
    - Conditionally prompt for thresholds (e.g., only ask for `min_rating` if "Quality" filters are enabled).
    - **Social Media Prompts:** Ask which platforms to require and then ask for the logic (AND/OR).
    - Support selecting logic (AND/OR) at runtime for global filter combination.
3.  **Progress Tracking:** Use `rich.progress` to show file reading and filter application status.

## Group 4: Export Engine
1.  **JSONL Writer:** Standard `aiofiles` or `with open` loop to write filtered nested data.
2.  **Pandas Integration:** Load filtered data into a DataFrame and use `to_csv` and `to_excel`.
3.  **File Naming:** Auto-generate output filenames: `{input_name}_filtered.{ext}`.
4.  **Excel Styling:** Apply basic formatting (bold headers, auto-filter, auto-column-width).

## Group 5: Validation & Testing
1.  **Unit Tests:** Verify each filter rule individually with mock data.
2.  **Integration Test:** Run the script against a sample `bakery_shops.jsonl` and verify the output counts.
3.  **Format Check:** Open the generated `.xlsx` and `.csv` to ensure column headers and data alignment are correct.
