-- Adds the Notification History entity from the PRD (5.3), and the
-- uniqueness guarantee that "duplicate notifications should never be
-- sent for the same listing" (PRD 4.6): one row per (saved_search,
-- listing) pair, ever. This also makes the matching engine safe to
-- re-run after a crash -- a listing already notified for a given saved
-- search will never be notified again for it, regardless of how many
-- times the scraper re-processes that listing.
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

create table if not exists notification_history (
    id uuid primary key default gen_random_uuid(),
    saved_search_id uuid not null references saved_searches(id) on delete cascade,
    listing_id uuid not null references listings(id) on delete cascade,
    notified_at timestamp with time zone default now(),
    unique (saved_search_id, listing_id)
);
