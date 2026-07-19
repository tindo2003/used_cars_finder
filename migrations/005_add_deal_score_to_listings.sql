-- Persists the "good deal" signal (scraper/deals.py) onto each listing
-- row, so the frontend can sort/badge on it directly instead of
-- reimplementing the heuristic in TypeScript. Computed and written back
-- once daily by scraper/notify.py (see deals.update_deal_scores).
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

alter table listings
  add column if not exists deal_score numeric,
  add column if not exists is_good_deal boolean not null default false;
