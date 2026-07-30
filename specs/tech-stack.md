# Tech Stack

## Current Stack (Implemented)

| Layer | Technology | Role |
|-------|-----------|------|
| Scraping engine | Playwright (async) | Headless Chromium, stealth injection, browser lifecycle |
| HTTP client | httpx (async) | Fast website fetching for email/social extraction |
| Data models | Pydantic v2 | Typed business schema, validation, serialization |
| Retry logic | Tenacity | Exponential backoff on flaky selectors / network errors |
| File I/O | aiofiles | Async JSONL incremental writes, atomic progress saves |
| Terminal UI | Rich | Progress bars, colored logs, session summaries |
| Storage | JSON / JSONL files | Output per-run; no persistent database yet |
| Proxy support | Flat `proxies.txt` | Manual list; no health checks or rotation management |

## Planned Stack (Not Yet Implemented)

| Layer | Technology | Notes |
|-------|-----------|-------|
| API layer | FastAPI | REST endpoints to trigger scrapes, query results, manage jobs |
| Task queue | Celery + Redis | Async job execution so long scrapes don't block the API |
| Database | PostgreSQL (or SQLite for local) | Persistent lead storage, deduplication, filtering, search |
| Frontend | Next.js | Web UI for non-developers; job control, lead browser, exports |
| Auth | TBD | Deferred — single-user for now; revisit when multi-user is needed |

## Key Gaps to Address (Priority Order)

### 1. Database Layer
Results currently live in per-run JSON files. There is no way to search across runs, deduplicate leads globally, or query by field. A database (PostgreSQL recommended for production; SQLite acceptable for local-only use) is the foundational gap before any other feature makes sense.

### 2. Task Queue (Celery + Redis)
FastAPI is async but a scrape job can run for minutes to hours. Without Celery, the API would block or time out. Redis serves double duty: Celery broker and potential cache for job status / dedup sets.

### 3. FastAPI Layer
Wraps the existing `scraper/api.py` in HTTP endpoints. Scrape jobs become POST requests; results are fetched via GET. This is the bridge between the Python scraping core and the Next.js frontend.

### 4. Next.js Frontend
The end-state UI: submit queries, monitor live job progress, browse/filter/export results. Consumes the FastAPI layer.

## Intentionally Deferred

- **Proxy management** — no residential proxies in use; flat file is sufficient. Revisit if detection rates increase.
- **Auth / multi-user** — single operator; no need for API keys or user accounts yet.
- **Billing / quotas** — out of scope until the platform serves external users.
