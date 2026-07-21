-- Phase 2 of radius search. Must run AFTER migration 015 (needs
-- listings.location to already exist) -- adds the GIST index 015
-- deliberately deferred ("add one alongside whatever migration actually
-- implements radius search" -- this is that migration), plus the
-- nearby_listings() function the frontend calls via supabase-js's
-- .rpc(). Idempotent, same as every migration in this project.
--
-- Run this once in the Supabase SQL editor (Dashboard > SQL Editor),
-- after migration 015.

create index if not exists listings_location_gist_idx
  on listings using gist (location);

-- Returns setof listings (not a custom shape) so supabase-js can chain
-- ordinary PostgREST filters (.eq, .is, .order, .range) directly onto
-- .rpc("nearby_listings", ...) exactly like a plain table query -- see
-- app/page.tsx's buildListingsQuery. Deliberately spatial-only: does
-- NOT filter status/duplicate_of itself, so that filtering logic isn't
-- duplicated in two places -- buildListingsQuery's existing chained
-- filters already apply on top of whatever this returns, same as they
-- do today against .from("listings").
create or replace function nearby_listings(center_lat float, center_lng float, radius_miles float)
returns setof listings
language sql
stable
as $$
  select *
  from listings
  where location is not null
    and ST_DWithin(
      -- location is geometry, not geography -- ST_DWithin on raw
      -- geometry measures in degrees, not real-world distance, so both
      -- sides are cast to geography for an accurate meters comparison.
      location::geography,
      ST_SetSRID(ST_MakePoint(center_lng, center_lat), 4326)::geography,
      radius_miles * 1609.34
    )
$$;

-- Uncomment and run if calling this from the anon/authenticated PostgREST
-- role fails with a permissions error (Supabase usually exposes new
-- public-schema functions to these roles by default, but confirm live):
-- grant execute on function nearby_listings(float, float, float) to anon, authenticated;
