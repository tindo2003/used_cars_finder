-- Documents already-live state -- predates the migrations/ convention,
-- same situation as saved_searches.user_id (see migration 010). The
-- PostGIS extension and both geometry columns were already set up ad hoc
-- via the Supabase dashboard before this file existed; nothing here needs
-- to actually change on production. This file exists purely so
-- migrations/ matches what's live, per this project's established rule
-- that predating-the-convention columns still get documented here.
--
-- `if not exists` everywhere makes this idempotent/harmless to run
-- against a DB that already has this state, or a genuinely fresh one.
--
-- Deliberately no spatial (GIST) index yet -- nothing queries by
-- location/target_location as of this migration (see scraper/geocoding.py,
-- which only writes it); add one alongside whatever migration actually
-- implements radius search.
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

create extension if not exists postgis;

alter table listings
  add column if not exists location geometry(Point, 4326);

alter table saved_searches
  add column if not exists target_location geometry(Point, 4326);
