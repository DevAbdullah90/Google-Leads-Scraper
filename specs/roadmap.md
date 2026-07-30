# Roadmap

## Already Implemented

- Google Maps scraping via Playwright (stealth, anti-detection)
- 15+ fields extracted per business: name, address, phone, website, rating, hours, category, coordinates, place ID, images, review count, attributes
- Email extraction: httpx fast-path + Playwright fallback for JS-heavy sites
- Social media extraction: Facebook, Instagram, Twitter/X, LinkedIn, YouTube, TikTok
- Geographic grid search: overcomes Google's ~120 result cap by subdividing areas into cells
- Empty cell detection: skips unpopulated geographic areas (water, forest, deserts) via OSM data
- Crash recovery: atomic `progress.json` checkpoints + incremental JSONL writes
- Resume support: pick up a crashed scrape from last saved position
- Proxy rotation: flat-file `proxies.txt`, http/https/socks5 with auth support
- User agent rotation: randomized UA + viewport per session
- Browser restart every 100 businesses (fresh fingerprint)
- Long break every 40 businesses (human-like pacing)
- CLI: `--query`, `--file`, `--interactive`, `--resume` modes
- Programmatic API: 5 wrapper functions (async, bulk, sync, grid, class-based)
- Rich terminal UI: progress bars, session summaries
- Rotating file logger: dual-stream (console INFO + file DEBUG), 10MB cap

---

## Phases

### Phase 1 — Lead Filtration & Format Conversion
*Goal: extract value from scraped JSONL files by filtering, deduplicating, and exporting to client-ready formats.*

- [ ] Interactive filtration CLI (`filter_leads.py`)
- [ ] Multi-criteria filtering: contact info (phone/email/website), ratings, reviews
- [ ] Category-based filtering: whitelist/blacklist with unique category discovery
- [ ] Keyword-based filtering (name/description)
- [ ] In-memory deduplication by Place ID
- [ ] Multi-format export: JSONL, CSV, and Excel (.xlsx)

### Phase 2 — Database Layer
*Goal: stop losing data between runs; enable deduplication and search.*

- [ ] Choose and set up database (PostgreSQL for production, SQLite for local)
- [ ] Define schema: `leads` table mirroring the existing Pydantic `Business` model
- [ ] Write persistence layer: save each scraped business to DB instead of / in addition to JSON
- [ ] Global deduplication: detect duplicate leads across queries (by phone, website, or place ID)
- [ ] Basic query API: filter leads by city, category, rating, has_email, has_phone, etc.

### Phase 2 — Task Queue
*Goal: scrape jobs run in the background without blocking the API. Must be in place before FastAPI is built so job handling is correct from day one.*

- [ ] Stand up Redis
- [ ] Integrate Celery; move scrape execution into a Celery task
- [ ] Job status updates written to Redis / DB (pending → running → done / failed)
- [ ] Handle job cancellation

### Phase 3 — FastAPI Layer
*Goal: expose scraping and lead data over HTTP so a frontend (or any client) can drive the platform. Built on top of the DB and Celery infrastructure from Phases 1–2.*

- [ ] `POST /jobs` — submit a scrape job (query + location + options)
- [ ] `GET /jobs/{id}` — poll job status and progress (reads live progress from Redis)
- [ ] `GET /leads` — paginated lead listing with filters
- [ ] `GET /leads/{id}` — single lead detail
- [ ] `DELETE /leads/{id}` — remove a lead
- [ ] `DELETE /jobs/{id}` — cancel a running job
- [ ] `GET /export` — export filtered leads as CSV or JSON

### Phase 4 — Web Frontend (Next.js)
*Goal: a no-code interface; full control without touching the CLI.*

- [ ] Job submission form: query, location, max results, grid toggle
- [ ] Live job progress view (poll or WebSocket)
- [ ] Lead browser: sortable/filterable table, column visibility toggle
- [ ] Lead detail panel: all fields, social links, open website
- [ ] Export button: CSV / Excel download
- [ ] Analytics dashboard: leads by city, category, rating distribution, email hit rate

### Phase 5 — Lead Scoring
*Goal: automatically rank leads so the best prospects surface first.*

- [ ] Define scoring model: weighted signals (has_email, has_phone, has_website, rating ≥ 4.0, review_count, social presence, category match)
- [ ] Compute `score` (0–100) and `score_grade` (A/B/C/D) on every lead at save time
- [ ] Re-score existing leads when the scoring weights are updated
- [ ] Expose score as a sortable/filterable column in the lead browser
- [ ] Score breakdown tooltip: show which signals contributed and how much
- [ ] Custom scoring rules: let the operator adjust weights per campaign (e.g. email matters more than rating for cold outreach)

### Phase 6 — Data Quality & Enrichment
*Goal: higher-quality leads, fewer dead ends.*

- [ ] Data validation dashboard: flag leads with missing email, phone, or website
- [ ] Duplicate merge UI: review and merge near-duplicate leads
- [ ] Re-enrich: re-run email/social extraction on existing leads without re-scraping Google
- [ ] Bulk edit: tag, annotate, or status-label leads (e.g. "contacted", "not interested")

### Phase 7 — Scheduling & Automation
*Goal: hands-off recurring lead collection.*

- [ ] Cron-based scrape scheduler: define a query + schedule (daily, weekly)
- [ ] Change detection: re-scrape known businesses and flag updated fields
- [ ] Webhook support: POST to a URL when a job completes

### Phase 8 — Export Integrations
*Goal: push leads directly into the tools where outreach happens.*

- [ ] Google Sheets export
- [ ] Airtable export
- [ ] Excel / XLSX download
- [ ] SQLite export
- [ ] CRM webhook (generic JSON POST)

### Phase 9 — Additional Scraping Sources
*Goal: more lead sources beyond Google Maps.*

- [ ] Yellow Pages / Yelp scraper
- [ ] LinkedIn company search (with caution re: ToS)
- [ ] Industry-specific directories (TBD based on use case)
- [ ] Unified source abstraction: each source implements the same scraper interface
