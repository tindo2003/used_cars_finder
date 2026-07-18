-- Fixes the listings duplication bug found 2026-07-18.
--
-- Root cause: scraper/main.py upserted with `on_conflict="vin"`, but
-- craigslist/eBay listings never have a vin (Postgres never treats two
-- NULLs as conflicting), so every scrape run inserted a fresh duplicate
-- row for the same ad instead of updating the existing one. The app code
-- has been changed to upsert on `original_url` instead, which is NOT NULL
-- and unique per listing regardless of source. This migration:
--   1. Removes the duplicate rows that already accumulated, keeping the
--      earliest-created row per original_url.
--   2. Adds a unique constraint on original_url so the new upsert target
--      is enforceable at the DB level.
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

-- Step 1: remove duplicates, keeping the oldest row per original_url
delete from listings
where id in (
  select id from (
    select id, row_number() over (
      partition by original_url
      order by created_at asc
    ) as rn
    from listings
  ) ranked
  where ranked.rn > 1
);

-- Step 2: enforce uniqueness so future upserts can target original_url
alter table listings
  add constraint listings_original_url_key unique (original_url);
