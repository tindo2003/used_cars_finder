-- Real auth now exists, so replace the no-auth stopgap (migration 004)
-- with policies scoped to the authenticated owner instead of the anon
-- key + `true`. saved_searches already has a `user_id` column (predates
-- the migrations/ convention, was NULL on all rows until now).
--
-- If the anon insert policy from initial table setup isn't named
-- "Allow anon insert", find its real name first with:
--   select policyname from pg_policies where tablename = 'saved_searches';
-- and drop that instead.
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

drop policy if exists "Allow anon select" on saved_searches;
drop policy if exists "Allow anon delete" on saved_searches;
drop policy if exists "Allow anon insert" on saved_searches;

alter table saved_searches enable row level security;

create policy "Owner can select" on saved_searches
  for select
  to authenticated
  using (auth.uid() = user_id);

create policy "Owner can insert" on saved_searches
  for insert
  to authenticated
  with check (auth.uid() = user_id);

create policy "Owner can update" on saved_searches
  for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "Owner can delete" on saved_searches
  for delete
  to authenticated
  using (auth.uid() = user_id);

-- One-off backfill for the 3 pre-auth rows (all have user_id IS NULL
-- today) -- run manually after signing up for the first real account,
-- substituting that account's UUID (Authentication > Users in the
-- Supabase dashboard):
--
--   update saved_searches set user_id = '<new-user-uuid>' where user_id is null;
