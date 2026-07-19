-- Adds last_seen_at, stamped by scraper/db.py's upsert() on every
-- insert *and* update. This is the source of truth for two features:
--   - scraper/staleness.py expires (marks non-active) listings that
--     haven't been reconfirmed in a configurable number of days -- the
--     working assumption is that a listing we keep re-scraping is more
--     likely still available than one we haven't seen in a long time.
--   - scraper/deals.py's ranking_key uses it as a tiebreaker (not the
--     primary sort) so that among equally-good matches, the one most
--     recently reconfirmed is preferred.
--
-- Defaults existing rows to now() at migration time (we don't know
-- their true last-seen time retroactively; treating them as freshly
-- seen avoids immediately expiring the whole table).
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

alter table listings
  add column if not exists last_seen_at timestamptz not null default now();
