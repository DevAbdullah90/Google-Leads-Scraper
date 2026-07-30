# Google Maps Business Leads Scraper

A production-grade tool for extracting business leads from Google Maps, with filtering, export to Google Sheets, and automated email outreach.

---

## Quick Start

```bash
# Clone the repository
git clone https://github.com/DevAbdullah90/Google-Leads-Scraper.git
cd Google-Leads-Scraper

# Create and activate virtual environment (Windows)
python -m venv venv
venv\Scripts\activate

# On Linux/macOS:
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run your first scrape
python main.py --query "real estate agents in Abu Dhabi" --max-results 50
```

---

## Table of Contents

- [Scraper Commands](#scraper-commands)
- [Export to Google Sheets](#export-to-google-sheets)
- [Filter Leads](#filter-leads)
- [Email Outreach](#email-outreach)
- [Grid Search](#grid-search)
- [Output Files](#output-files)
- [Configuration](#configuration)

---

## Scraper Commands

### Basic Usage

```bash
# Single query
python main.py --query "restaurants in Dubai" --max-results 100

# Interactive mode (prompts for niche and location)
python main.py --interactive

# From file (queries.txt or queries.csv)
python main.py --file queries.txt

# Resume interrupted scrape
python main.py --resume
```

### Command Line Options

| Flag | Description | Example |
|------|-------------|---------|
| `-q, --query` | Single search query | `--query "coffee shops in Dubai"` |
| `-f, --file` | CSV/TXT file with queries | `--file queries.csv` |
| `-i, --interactive` | Interactive prompt mode | `--interactive` |
| `-r, --resume` | Resume last session | `--resume` |
| `-m, --max-results` | Max results per query | `--max-results 50` |
| `-p, --proxy-file` | Proxy list file | `--proxy-file proxies.txt` |
| `--proxy` | Single proxy URL | `--proxy http://user:pass@host:port` |
| `--headless` | Run headless (default: on) | `--no-headless` |
| `--delay` | Delay between requests (sec) | `--delay 5` |
| `--debug` | Enable debug logging | `--debug` |

### Example Commands

```bash
# Scrape 50 real estate agents in Dubai
python main.py --query "real estate agents in Dubai" --max-results 50

# Scrape multiple queries from file
python main.py --file queries.txt --max-results 100

# Scrape with proxy
python main.py --query "restaurants in Abu Dhabi" --proxy-file proxies.txt

# Interactive mode with debug
python main.py --interactive --debug
```

---

## Export to Google Sheets

```bash
# Export latest scrape to Google Sheets
python export_to_sheets.py

# Export specific file
python export_to_sheets.py output/real_estate_agents_in_abu_dhabi.json

# Export with custom spreadsheet ID
python export_to_sheets.py output/leads.json --spreadsheet-id YOUR_SHEET_ID
```

### Spreadsheet Structure

| Column | Field |
|--------|-------|
| A | Business Name |
| B | Phone |
| C | Email |
| D | Website |
| E | Category |
| F | Rating |
| G | Reviews |
| H | Full Address |
| I | Google Maps URL |
| J | Status (SENT/FAILED) |
| K | Sent Date |

---

## Filter Leads

```bash
# Interactive filtering
python filter_leads.py output/leads.json --interactive

# Filter with phone and email required
python filter_leads.py output/leads.json --phone --email

# Filter by rating
python filter_leads.py output/leads.json --min-rating 4.5 --min-reviews 50

# Filter by category
python filter_leads.py output/leads.json --whitelist "Real estate agency,Real estate agent"

# Filter by social media
python filter_leads.py output/leads.json --socials "instagram,facebook"
```

### Filter Options

| Flag | Description |
|------|-------------|
| `--phone` | Require phone number |
| `--website` | Require website |
| `--email` | Require email |
| `--min-rating` | Minimum rating (0-5) |
| `--min-reviews` | Minimum review count |
| `--whitelist` | Categories to keep (comma-separated) |
| `--blacklist` | Categories to exclude (comma-separated) |
| `--keywords` | Keywords to search for |
| `--socials` | Required social platforms |
| `--social-logic` | AND/OR for social requirements |
| `--logic` | Global AND/OR logic |
| `--no-dedup` | Disable deduplication |

---

## Email Outreach

### Quick Start

In a new session, simply say:

```
Email the latest leads
```

Or:

```
Use the real-estate-outreach skill to email unsent leads
```

### What Happens

1. Reads your Google Sheet
2. Finds leads where Status (Column J) is empty
3. Generates personalized emails
4. Sends via Zoho Mail
5. Marks sent leads as `SENT` with green background
6. Generates summary report

### Manual Email Commands

```bash
# Mark specific rows as sent
python scripts/mark_sent.py SPREADSHEET_ID 2 11

# Apply green background
python scripts/apply_color.py SPREADSHEET_ID "Scraped Leads" 2 11 green

# Apply red background (for failures)
python scripts/apply_color.py SPREADSHEET_ID "Scraped Leads" 5 5 red
```

### Email Configuration

- **Account ID**: `603147200000008002`
- **From Address**: `info@nexeagent.com`
- **Signature**: `config/email_signature.html`

---

## Grid Search

Grid search overcomes Google's ~60-120 result limit by dividing the area into cells.

```bash
# Enable grid search
python main.py --query "real estate agents in Dubai" --grid --cell-size 2.0

# With bounds
python main.py --query "real estate agents in Dubai" --grid --bounds "25.358,24.793,55.565,54.890"

# With smart filter (skip empty areas)
python main.py --query "real estate agents in Dubai" --grid --smart-filter

# Adaptive grid (subdivide crowded cells)
python main.py --query "real estate agents in Dubai" --grid --adaptive --max-results 50

# Estimate time only (no scraping)
python main.py --query "real estate agents in Dubai" --grid --estimate-only

# Preview filter results
python main.py --query "real estate agents in Dubai" --grid --filter-preview
```

### Grid Options

| Flag | Description | Default |
|------|-------------|---------|
| `--grid` | Enable grid search | off |
| `--cell-size` | Cell size in km | 2.0 |
| `--bounds` | Bounding box (N,S,E,W) | auto |
| `--adaptive` | Subdivide crowded cells | off |
| `--smart-filter` | Skip empty areas | off |
| `--filter-method` | Detection method | auto |
| `--min-buildings` | Min buildings for OSM check | 5 |
| `--estimate-only` | Print estimate, exit | off |
| `--filter-preview` | Sample filter results | off |

---

## Output Files

After each scrape, files are saved to `output/`:

| File | Format | Description |
|------|--------|-------------|
| `*.json` | JSON | Full structured data |
| `*.jsonl` | JSONL | Line-by-line JSON |
| `*.csv` | CSV | Spreadsheet compatible |
| `*.xlsx` | Excel | Formatted workbook |

---

## Configuration

### Queries File

Create `queries.txt` with one query per line:

```
real estate agents in Dubai, UAE
real estate agents in Abu Dhabi, UAE
restaurants in New York, NY
```

Or CSV format (`queries.csv`):

```csv
query
real estate agents in Dubai
restaurants in New York
```

### Proxies

Create `proxies.txt` with one proxy per line:

```
http://user:pass@host:port
http://user:pass@host:port
```

---

## Project Structure

```
Google-Leads-Scraper/
├── main.py                 # Scraper CLI entry point
├── export_to_sheets.py     # Export to Google Sheets
├── filter_leads.py         # Filter and process leads
├── requirements.txt        # Python dependencies
├── queries.txt             # Search queries
├── proxies.txt             # Proxy list
├── credentials.json        # Google API credentials
├── config/
│   ├── settings.py         # App settings
│   └── email_signature.html # Email signature
├── scraper/
│   ├── api.py              # Main scraper logic
│   ├── grid.py             # Grid search
│   └── ...
├── scripts/
│   ├── apply_color.py      # Apply sheet formatting
│   └── mark_sent.py        # Mark leads as sent
├── real-estate-outreach/   # Email outreach skill
│   ├── SKILL.md
│   ├── scripts/
│   └── references/
├── output/                 # Scraped JSON files
└── data/                   # Data storage
```

---

## Troubleshooting

### "No progress.json found"
- Use `--resume` only after an interrupted scrape

### "Could not resolve bounds"
- Add city name to query: `"real estate agents in Dubai, UAE"`
- Or use `--country UAE`

### Google Sheets access denied
- Share sheet with service account email from `credentials.json`
- Set role to "Editor"

### Email not sending
- Check `config/email_signature.html` exists
- Verify Zoho Mail MCP is configured in `opencode.jsonc`

---

## License

Internal use only.
