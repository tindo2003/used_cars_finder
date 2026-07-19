-- listings.original_url has had a table-wide unique constraint since
-- migration 001, from back when original_url was the only conflict key.
-- Migration 007 moved dealer-sourced upserts to (vin, dealer_name), but
-- original_url's own separate uniqueness stuck around -- and it no
-- longer matches reality: a dealer's own inventory card can legitimately
-- link to a DIFFERENT dealer's page for the same syndicated vehicle
-- (observed live: a Capitol Honda card linking to
-- chevroletoffremont.com). scraper/db.py was catching the resulting
-- 23505 violation and skipping the row entirely -- which meant the
-- second dealer's listing was never inserted at all, so
-- scraper/duplicates.py's exact-VIN-match pass (built specifically to
-- flag this case via duplicate_of) never got a chance to see it.
--
-- scraper/db.py no longer relies on original_url being globally unique:
-- dealer rows (have a vin) keep upserting on (vin, dealer_name)
-- unchanged; VIN-less rows (Craigslist) now dedupe with a manual
-- lookup-by-original_url instead of a native ON CONFLICT. So this
-- constraint can just be dropped, replaced with a plain (non-unique)
-- index to keep lookups by original_url fast.
--
-- Migration 007/008 previously guessed a constraint name wrong and
-- needed a follow-up fix -- this one looks the constraint up by its
-- actual definition instead of guessing its name.
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

do $$
declare
    con_name text;
begin
    select conname into con_name
    from pg_constraint
    where conrelid = 'listings'::regclass
      and contype = 'u'
      and pg_get_constraintdef(oid) = 'UNIQUE (original_url)';

    if con_name is not null then
        execute format('alter table listings drop constraint %I', con_name);
    end if;
end $$;

create index if not exists idx_listings_original_url on listings (original_url);
