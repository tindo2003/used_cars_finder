-- Cross-marketplace duplicate detection (scraper/duplicates.py): the same
-- physical vehicle can appear on Craigslist and a dealer site with no
-- shared identifier. duplicate_of points a non-canonical listing at the
-- one to show instead; null means "not a known duplicate". Computed and
-- written back once daily by scraper/notify.py, same as deal_score.
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

alter table listings
  add column if not exists duplicate_of uuid references listings(id) on delete set null;
