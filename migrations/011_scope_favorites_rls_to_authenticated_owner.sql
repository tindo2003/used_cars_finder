-- Favorites (PRD 3.7/4.7): a lightweight per-account watchlist. The
-- favorites table already existed (user_id, listing_id, created_at)
-- but predates this migrations/ convention, so its RLS state was never
-- verified -- this establishes it explicitly rather than assuming,
-- same treatment migration 010 gave saved_searches.
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor).

alter table favorites enable row level security;

drop policy if exists "Owner can select" on favorites;
create policy "Owner can select" on favorites
  for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "Owner can insert" on favorites;
create policy "Owner can insert" on favorites
  for insert
  to authenticated
  with check (auth.uid() = user_id);

drop policy if exists "Owner can update" on favorites;
create policy "Owner can update" on favorites
  for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists "Owner can delete" on favorites;
create policy "Owner can delete" on favorites
  for delete
  to authenticated
  using (auth.uid() = user_id);

-- Prevents favoriting the same listing twice.
create unique index if not exists favorites_user_id_listing_id_key on favorites (user_id, listing_id);
