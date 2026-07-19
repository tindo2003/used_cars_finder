-- Fixes a "ghost location" bug: dealer groups can syndicate the same
-- physical vehicle's VIN across multiple storefronts they own (e.g. a
-- trade-in shows up on both "Capitol Honda" and sister store "Capitol
-- Ford"). scraper/main.py upserted with on_conflict="vin", so the
-- second store's scrape silently overwrote the first store's
-- dealer_name/city/original_url in place -- one row that flip-flops
-- location with no visible duplicate and no history of the swap.
--
-- scraper/db.py now upserts dealer-sourced listings on (vin,
-- dealer_name) instead, so each storefront's listing survives as its
-- own row; scraper/duplicates.py flags same-VIN rows across dealers as
-- duplicates explicitly (see its exact-VIN match rule) rather than the
-- database silently merging them.
--
-- Safe to run as-is: as of 2026-07-20 no VIN appears more than once
-- across active listings, so there's nothing to reconcile. If this
-- errors with "constraint does not exist", find the actual constraint
-- name first with:
--   select conname from pg_constraint where conrelid = 'listings'::regclass and contype = 'u';
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

alter table listings drop constraint if exists listings_vin_key;

alter table listings
  add constraint listings_vin_dealer_name_key unique (vin, dealer_name);
