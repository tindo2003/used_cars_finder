-- Relaxes RLS on saved_searches so the no-auth frontend can list and
-- delete searches by id (tracked client-side in localStorage, since
-- there's no real user account to scope rows to yet).
--
-- Tradeoff, accepted as a deliberate product decision on 2026-07-19:
-- every row in this table (including the email address) becomes
-- readable and deletable via the public REST API to anyone who calls
-- it directly, not just through this app's UI -- RLS can't distinguish
-- "the frontend filtered by a known id" from "a random caller asked for
-- everything." Revisit once real auth exists (see
-- research/mvp-checklist.md) and scope these policies to the
-- authenticated owner instead of `true`.
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

drop policy if exists "Allow anon select" on saved_searches;
create policy "Allow anon select" on saved_searches
  for select
  to anon
  using (true);

drop policy if exists "Allow anon delete" on saved_searches;
create policy "Allow anon delete" on saved_searches
  for delete
  to anon
  using (true);
