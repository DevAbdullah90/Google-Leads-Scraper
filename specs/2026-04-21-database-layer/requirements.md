# Requirements — Database Layer

## Scope

### What is included
- SQLite as the primary datastore (single file, zero setup, local use)
- A `leads` table that mirrors every field in the existing Pydantic `Business` model
- Async persistence layer: each scraped business is upserted into the DB instead of written to JSONL inline
- Global deduplication across runs and queries (by `place_id` as primary key; `phone` and `website` as secondary signals)
- Basic query/filter API: filter leads by city, category, rating, `has_email`, `has_phone`, etc.
- On-demand export: generate JSONL or CSV from DB rows (replaces the current inline JSONL write)

### What is NOT included
- PostgreSQL support (deferred — SQLAlchemy abstraction makes it addable later via env var swap)
- A web API or CLI command for querying leads (that is Phase 3 — FastAPI)
- A frontend or any UI (Phase 4)
- Auth or multi-user isolation (intentionally deferred per mission)

### Data shape — `leads` table

| Column | Type | Source |
|--------|------|--------|
| `id` | INTEGER PK autoincrement | DB-generated |
| `place_id` | TEXT UNIQUE NOT NULL | `Business.place_id` — dedup key |
| `name` | TEXT | `Business.name` |
| `address` | TEXT | `Business.address` |
| `city` | TEXT | parsed from address |
| `phone` | TEXT | `Business.phone` |
| `website` | TEXT | `Business.website` |
| `email` | TEXT | `Business.email` |
| `rating` | REAL | `Business.rating` |
| `review_count` | INTEGER | `Business.review_count` |
| `category` | TEXT | `Business.category` |
| `latitude` | REAL | `Business.latitude` |
| `longitude` | REAL | `Business.longitude` |
| `hours` | TEXT (JSON) | `Business.hours` serialized |
| `attributes` | TEXT (JSON) | `Business.attributes` serialized |
| `images` | TEXT (JSON) | `Business.images` serialized |
| `facebook` | TEXT | `Business.facebook` |
| `instagram` | TEXT | `Business.instagram` |
| `twitter` | TEXT | `Business.twitter` |
| `linkedin` | TEXT | `Business.linkedin` |
| `youtube` | TEXT | `Business.youtube` |
| `tiktok` | TEXT | `Business.tiktok` |
| `source_query` | TEXT | query string that produced this lead |
| `scraped_at` | DATETIME | timestamp of upsert |

---

## Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Database | SQLite | Zero setup; single-operator use; file is portable; SQLAlchemy makes Postgres swap trivial later |
| ORM | SQLAlchemy (async) + Alembic | Industry standard; migration support; works with both SQLite and Postgres; async-native via `aiosqlite` |
| Write strategy | DB primary, JSONL/CSV on export only | Eliminates dual-write complexity; JSONL is now a view over the DB, not a source of truth |
| Deduplication key | `place_id` (UNIQUE constraint) | Google place IDs are stable and globally unique; upsert on conflict updates stale fields |
| Secondary dedup | Warn on matching `phone` or `website` when `place_id` differs | Catches businesses listed under slightly different names or locations |
| City extraction | Parse from `address` field at save time | Avoids adding a geocoding dependency; good enough for filtering |
| JSON columns | Serialize to TEXT as JSON strings | SQLite has no native JSON array type; keeps schema simple; SQLAlchemy handles ser/de |

---

## Context

- **Stack constraint**: async throughout — use `sqlalchemy[asyncio]` + `aiosqlite` driver; no sync DB calls in the scrape hot path
- **Existing pattern to follow**: the scraper already uses `aiofiles` for async I/O; the DB layer should feel the same — an `await db.save(business)` call, not a context-manager maze
- **Pydantic v2**: the existing `Business` model is Pydantic v2; use `.model_dump()` to convert to dict before persisting
- **Migration discipline**: every schema change goes through Alembic, even in development — no `create_all()` in production paths
- **DB file location**: default to `data/leads.db` relative to project root; configurable via `DATABASE_URL` env var
