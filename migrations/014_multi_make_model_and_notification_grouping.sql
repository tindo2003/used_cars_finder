-- Product decision 2026-07-20: saved searches should support more than
-- one make/model at a time (e.g. "Toyota or Lexus", "Camry or ES"), so
-- saved_searches.make/model move from scalar `text` to `text[]`. The
-- USING clause wraps any existing single value in a one-element array
-- so existing saved searches keep matching exactly what they did
-- before this migration. listings.make/model are untouched -- a single
-- vehicle only ever has one make/model, only the *filter* side needed
-- to become multi-valued.
--
-- Also adds notification_grouping so a saved search with multiple
-- makes/models can choose to get one combined daily digest (default,
-- today's behavior), or one separate email per distinct make/model
-- among its matches.
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

alter table saved_searches
  alter column make type text[] using case when make is null then null else array[make] end,
  alter column model type text[] using case when model is null then null else array[model] end;

alter table saved_searches
  add column notification_grouping text not null default 'combined'
    check (notification_grouping in ('combined', 'make', 'model'));
