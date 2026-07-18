-- Adds a human-readable dealership name to listings, so the UI can show
-- "Capitol Honda" instead of the raw platform code ("dealerinspire").
-- Populated by the scraper for dealer-sourced listings (from DEALERS'
-- "name" entry in scraper/main.py); left null for marketplace sources
-- like Craigslist, which aren't a single dealership.
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

alter table listings
  add column if not exists dealer_name text;
