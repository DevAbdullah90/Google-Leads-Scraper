# Remaining Work — Phase 1: Database Layer

This document tracks the missing pieces required to fully complete Phase 1 of the roadmap.

## 1. Scraper-Database Integration
- [ ] Update `GoogleMapsScraper` in `scraper/api.py` to accept an optional database session.
- [ ] Call `upsert_lead` from `db/repository.py` inside the scraping loop.
- [ ] Ensure that even if DB save fails, the JSONL backup still happens (and vice-versa).

## 2. Table Initialization
- [ ] Add a utility function to `db/engine.py` or a standalone script to run `Base.metadata.create_all(engine)` to ensure tables exist before the first run.
- [ ] Consider adding `alembic` if schema migrations are expected to be frequent.

## 3. CLI Enhancements
- [ ] Add a `--db` or `--no-db` flag to `main.py`.
- [ ] Implement a "Smart Deduplication" feature: check the DB for `place_id` *before* the browser visits a business URL to save time and resources.

## 4. Schema Alignment
- [ ] Add a `reviews` column (JSON/Text) to the `Lead` model in `db/models.py`.
- [ ] Update `_flatten` in `db/repository.py` to include review data.

## 5. Testing & Validation
- [ ] Verify that `on_conflict_do_update` correctly handles duplicates without throwing errors.
- [ ] Test the "Secondary Duplicate" warning system (shared phone/website) with real data.
