# Requirements: Lead Filtration & Format Conversion

## Scope
The goal is to provide a robust utility to process scraped lead data (JSONL) into high-quality, filtered datasets in multiple formats (JSONL, CSV, Excel).

### Included
- **Input:** Single or multiple JSONL files produced by the scraper.
- **Deduplication:** Global deduplication by `place_id`.
- **Filtering Logic:**
    - **Contact Info:** Optional/Mandatory phone, website, and email.
    - **Quality Metrics:** Dynamic prompts for minimum average rating and review counts (only asked if the filter category is selected).
    - **Categories:** 
        - Discovery of all unique categories in the dataset.
        - Whitelist and Blacklist modes.
        - **Dual Input:** Choose via a numbered list of discovered categories OR manual text input.
    - **Keywords:** Case-insensitive search in business name and description.
    - **Social Media:** 
        - Select specific platforms (Facebook, Instagram, LinkedIn, etc.) to require.
        - **Logic:** Choose between **AND** (must have all selected) or **OR** (must have at least one of the selected).
- **Logic Handling:** Support for both **AND** (strict) and **OR** (flexible) logic when multiple filters are applied.
- **Execution Modes:**
    - **Interactive:** Highly dynamic session using `rich`. Only prompts for specific values (like min-rating) if that filter category is activated.
    - **CLI Arguments:** Power-user support for automated or quick filtering.
- **Output Formats:**
    - **JSONL:** Preserves the full nested structure.
    - **CSV:** Flattened structure for spreadsheet compatibility.
    - **Excel (.xlsx):** Flattened structure, professionally formatted with column auto-sizing and basic styling.

### Data Mapping (Flattening for Export)
| JSON Path | CSV/Excel Header |
|-----------|------------------|
| `business_name` | Business Name |
| `place_id` | Place ID |
| `google_maps_url` | Google Maps URL |
| `address.full_address` | Address |
| `address.city` | City |
| `address.state` | State |
| `address.postal_code` | Zip |
| `contact.phone` | Phone |
| `contact.website` | Website |
| `contact.email" | Email |
| `social_media.*` | Facebook, Instagram, etc. |
| `business_info.category` | Primary Category |
| `ratings.average_rating` | Rating |
| `ratings.total_reviews` | Reviews |

## Decisions
- **Hybrid Interface:** We will use `argparse` for flags and `rich.prompt` for interactive sessions. If flags are provided, it bypasses prompts for those specific filters.
- **Conditional Workflow:** In interactive mode, the user first selects *which* categories to filter by (e.g., "Quality"), then the script asks for the specific thresholds (e.g., "Min Rating").
- **File Naming:** Output files will follow the pattern: `[input_filename]_filtered.[extension]`.
- **Flattening:** Nested objects (address, contact, social) will be flattened into top-level columns to ensure the data is immediately actionable in outreach tools.
- **Dependencies:** `pandas` and `openpyxl` are approved for handling complex CSV/Excel transformations reliably.

## Context
- **Tone:** The CLI should feel like a professional tool, providing clear progress indicators and summaries of how many leads were "dropped" vs. "kept".
- **Stack:** Python 3.12+, Pydantic v2 for data validation, Pandas for export.
- **Pattern:** Follow the existing pattern of using `rich` for terminal output and `pathlib` for file handling.
