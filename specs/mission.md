# Mission

## What We're Building

An all-in-one lead generation platform that lets you find, enrich, manage, and export business leads from any source — starting with Google Maps, with more sources (LinkedIn, Yellow Pages, Yelp, etc.) added over time.

## Current State

A production-grade Google Maps scraper: given a search query and location, it extracts business name, address, phone, website, email, social media links, ratings, hours, and more — with anti-detection, crash recovery, and geographic grid search to overcome Google's result caps.

## North Star

A single platform where you can:
1. **Scrape** — trigger lead collection from any supported source
2. **Enrich** — auto-extract emails, socials, and additional data points
3. **Score** — rank leads automatically by quality signals (completeness, rating, review volume, etc.)
4. **Manage** — search, filter, deduplicate, and annotate leads in a database
5. **Export** — push to CSV, Excel, Google Sheets, Airtable, or a CRM

## Current Primary User

Personal use — the platform is run by a single operator for their own campaigns and lead generation workflows.

## Future Direction

As the platform matures, the target expands to solo founders and SDRs who need self-service lead generation without writing code. Multi-user and auth features are deferred until that transition.

## Guiding Principles

- **Reliability first** — scrapes should never silently fail; crash recovery and incremental saves are non-negotiable
- **Quality over quantity** — validated, deduplicated, enriched leads beat raw volume
- **Operator-friendly** — usable without reading docs; a web UI is the end goal
- **Extensible by design** — new sources, exporters, and enrichment steps should plug in without rewriting the core
