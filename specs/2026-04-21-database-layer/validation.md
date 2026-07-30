# Validation — Database Layer

## Automated

### Dependencies
- [ ] `pip install sqlalchemy[asyncio] aiosqlite alembic` succeeds with no conflicts

### Migrations
- [ ] `alembic upgrade head` on a blank DB creates the `leads` table with correct columns
- [ ] `alembic downgrade -1` drops the table cleanly
- [ ] `alembic upgrade head` again re-creates it (round-trip clean)

### Persistence
- [ ] `upsert_lead` inserts a new `Business` object and the row appears in DB
- [ ] `upsert_lead` called twice with the same `place_id` produces exactly one row (no duplicate)
- [ ] `upsert_lead` on an existing `place_id` with updated fields (e.g. changed phone) overwrites the stale values
- [ ] `scraped_at` timestamp is set on every upsert

### Deduplication
- [ ] Two businesses with the same `place_id` → one row in DB
- [ ] Two businesses with the same `phone` but different `place_id` → warning logged, both rows kept
- [ ] `dedup_existing()` correctly identifies and reports duplicate phone/website pairs in a seeded DB

### Query / Filter
- [ ] `get_leads(city="London")` returns only leads where city matches
- [ ] `get_leads(has_email=True)` returns only leads where `email` is not null/empty
- [ ] `get_leads(rating=4.0)` returns only leads with rating ≥ 4.0
- [ ] Combining filters works: `get_leads(city="London", has_email=True, rating=4.0)`

### Export
- [ ] `export_jsonl` produces a valid `.jsonl` file; each line parses as a JSON object with expected fields
- [ ] `export_csv` produces a valid `.csv` file with a header row and correct column count
- [ ] Export with filters produces a subset matching the filter (row count verifiable)
- [ ] CLI `export --format jsonl --output out.jsonl` runs without error

### Legacy Import
- [ ] `import_jsonl` on an existing JSONL output file inserts the correct number of rows
- [ ] Re-running import on the same file does not produce duplicates

---

## Manual Walkthrough

1. Run a real scrape for a small query (e.g. `--query "coffee shops" --location "Edinburgh" --max 20`)
2. Confirm no JSONL file is written mid-scrape (only on explicit export)
3. Open `data/leads.db` with a SQLite viewer (e.g. DB Browser for SQLite); confirm rows are present with correct fields
4. Run `export --format csv --output leads.csv`; open CSV and spot-check 3–5 rows against DB
5. Run the same scrape again (resume or re-run); confirm row count does not increase (dedup working)
6. Run `import` on an old JSONL file from a previous run; confirm rows are added without duplicates

---

## Edge Cases

- [ ] Scrape crashes mid-run: partial DB writes are committed (no rolled-back data loss); `progress.json` still allows resume
- [ ] `Business` field is `None` (e.g. no email found): persisted as NULL, not as the string `"None"`
- [ ] `hours`, `attributes`, `images` are dicts/lists: serialised to JSON string correctly; round-trips back to Python object on read
- [ ] DB file path does not exist: `data/` directory is created automatically on first run
- [ ] `DATABASE_URL` env var override points to a different SQLite file: engine uses that file instead of default

---

## Definition of Done

- All automated checks above pass
- Manual walkthrough completes without errors
- No JSONL files are written during a scrape run (only via explicit export)
- Existing crash-recovery (`progress.json`) behaviour is unchanged
- `alembic upgrade head` is the only setup step required beyond `pip install`
