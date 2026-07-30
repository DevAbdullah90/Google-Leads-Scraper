# Requirements — Simple Lead Export

## Scope
- **Input**: A JSON file containing a list of businesses (scraped leads).
- **Output**: 
    - A CSV file saved as `[input_filename]_exported.csv`.
    - An Excel (.xlsx) file saved as `[input_filename]_exported.xlsx`.
- **Flattening**: All nested objects (e.g., `address`, `contact`, `social_media`, `ratings`) must be flattened into top-level columns using a separator (default: `_`).
- **Dynamic Pruning**: Columns that are empty (None, null, empty string, or empty list/dict) across **all** records in the file must be dropped from the final export.
- **CLI Interface**:
    - Required argument: `input_file` (path to JSON).
    - Optional argument: `--output-dir` (target directory). Defaults to the input file's parent folder.

## Decisions
- **Libraries**: Use `pandas` for data manipulation and flattening, and `openpyxl` as the engine for Excel export.
- **Processing**: Load JSON into memory (acceptable for typical scrape sizes, e.g., < 10,000 leads).
- **Naming**: Use `_` as the separator for flattened keys (e.g., `contact_phone`, `address_city`).
- **Empty Value Handling**: Values that are entirely empty across the dataset are removed to keep the export clean for the end-user.

## Context
- **Tone**: The tool is a "path-in, files-out" utility.
- **Constraints**: Follow the existing Python 3.12 stack. No complex filtration logic; just robust data transformation.
- **Existing Patterns**: Reuse `Business` model logic if helpful, but the script should be robust enough to handle the raw JSON structure.
