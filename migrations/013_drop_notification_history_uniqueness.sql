-- notification_history's unique (saved_search_id, listing_id) constraint
-- (migration 002) enforced "never send the same listing twice for a
-- given saved search". Product decision 2026-07-20: the daily digest
-- should always send the current top N best-ranked matches for a saved
-- search, regardless of whether they were sent before -- a deal hunter
-- wants today's best matches, not just novel ones. scraper/notify.py no
-- longer reads this table to filter what gets sent; it's kept purely as
-- a log of what was sent when (for a possible future click-through-rate
-- metric), so it needs to allow more than one row per
-- (saved_search_id, listing_id) pair -- one per day it's included in a
-- digest.
--
-- Looks the constraint up by its actual definition rather than guessing
-- its name, the same way migration 012 did (learning from migration
-- 007/008's wrong-name guess).
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

do $$
declare
    con_name text;
begin
    select conname into con_name
    from pg_constraint
    where conrelid = 'notification_history'::regclass
      and contype = 'u'
      and pg_get_constraintdef(oid) = 'UNIQUE (saved_search_id, listing_id)';

    if con_name is not null then
        execute format('alter table notification_history drop constraint %I', con_name);
    end if;
end $$;
