-- Follow-up to migration 007: that migration guessed the vin-only
-- unique constraint was named listings_vin_key (Postgres's default
-- naming for a column-level `unique`), but the actual constraint is
-- named listings_vin_unique -- so the `drop constraint if exists
-- listings_vin_key` silently no-op'd and the old vin-only uniqueness
-- was still enforced, blocking two different dealers from ever sharing
-- a VIN (confirmed live via a synthetic test upsert 2026-07-20, which
-- failed with: duplicate key value violates unique constraint
-- "listings_vin_unique").
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

alter table listings drop constraint if exists listings_vin_unique;
