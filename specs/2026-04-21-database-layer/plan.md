# Plan — Database Layer

## Task Groups

### 1. Setup
1.1 Install dependencies: `sqlalchemy[asyncio]`, `aiosqlite`, `alembic`
1.2 Create `db/` package: `__init__.py`, `engine.py`, `models.py`, `session.py`
1.3 Configure async SQLAlchemy engine in `engine.py` — reads `DATABASE_URL` env var, defaults to `sqlite+aiosqlite:///data/leads.db`
1.4 Initialise Alembic: `alembic init alembic/`; point `alembic.ini` and `env.py` at the same `DATABASE_URL`

### 2. Schema & Migration
2.1 Define `Lead` ORM model in `db/models.py` — all columns from the requirements table; `place_id` UNIQUE NOT NULL
2.2 Write initial Alembic migration: `alembic revision --autogenerate -m "create leads table"`
2.3 Verify migration runs cleanly against a blank SQLite file: `alembic upgrade head`

### 3. Persistence Layer
3.1 Write `db/repository.py` with two async functions:
  - `upsert_lead(session, business, source_query)` — insert or update on `place_id` conflict
  - `get_leads(session, **filters)` — filter by city, category, rating, has_email, has_phone
3.2 Write `db/session.py`: async session factory (`async_sessionmaker`) and an `async with get_session()` context manager
3.3 Add city extraction helper: parse city from `address` string at upsert time

### 4. Scraper Integration
4.1 Locate where the scraper currently writes to JSONL (likely `scraper/core.py` or equivalent)
4.2 Replace the JSONL write call with `await upsert_lead(session, business, source_query=query)`
4.3 Remove inline JSONL write logic from the hot path; keep `progress.json` checkpoint writes untouched (crash recovery)
4.4 Open a single DB session per scrape run (not per business) and pass it through; close on completion or crash

### 5. Deduplication
5.1 `upsert_lead` handles primary dedup via `place_id` UNIQUE constraint (ON CONFLICT DO UPDATE)
5.2 Add secondary dedup check: after upsert, query for leads with same `phone` or `website` but different `place_id`; log a warning with both IDs
5.3 Write a one-off `dedup_existing()` utility to scan and report duplicates in an already-populated DB (useful after first migration of legacy JSONL data)

### 6. JSONL / CSV Export
6.1 Write `db/export.py` with:
  - `export_jsonl(session, path, **filters)` — stream filtered leads to a `.jsonl` file
  - `export_csv(session, path, **filters)` — stream filtered leads to a `.csv` file
6.2 Add a CLI subcommand `export` to the existing CLI: `--format jsonl|csv`, `--output <path>`, filter flags matching `get_leads`
6.3 On first run after migration, offer to import existing JSONL files into the DB via `import_jsonl(path)` helper

### 7. Legacy Data Import (one-time)
7.1 Write `db/importer.py`: read existing `*.jsonl` output files, parse each line as a `Business`, call `upsert_lead`
7.2 Add CLI subcommand `import` accepting a glob or directory path
7.3 Run import on existing data to seed the DB; verify row counts match JSONL line counts
