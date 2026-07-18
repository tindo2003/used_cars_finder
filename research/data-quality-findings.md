# Scraper Data Quality Findings

Found 2026-07-18 by exporting `listings` to CSV and inspecting it directly (118 rows: 86 dealerinspire / Capitol Honda, 20 craigslist, 12 dealeron / Stevens Creek Toyota, 0 eBay).

## Fixed

**Duplicate rows from non-VIN sources (critical, actively growing).** 18 of the 20 craigslist rows were re-inserts of just 5 unique listings — the same `original_url` appearing 3-4 times with different `id`/`created_at`. Root cause: `scraper/main.py`'s `save_cars_to_db` upserted with `on_conflict="vin"`, but craigslist/eBay listings never have a VIN, and Postgres never treats two `NULL`s as conflicting — so every scrape run inserted a fresh duplicate instead of updating. This would keep growing unbounded on every cron run.

Related latent bug: `dealeron.py` and `dealerinspire.py` defaulted missing VINs to the literal string `"Unknown"` rather than `None`. If two vehicles on the same dealer site ever both lacked a VIN, they'd collide under `on_conflict="vin"` and silently overwrite each other.

Fix applied:
- `scraper/main.py`: upsert conflict target changed from `vin` to `original_url` (always `NOT NULL`, unique per listing across every source seen so far).
- `dealeron.py` / `dealerinspire.py`: missing VIN now stored as `None` instead of `"Unknown"`.
- `migrations/001_dedupe_listings_and_fix_conflict_key.sql`: one-time cleanup of existing duplicates + adds the unique constraint on `original_url` the new upsert relies on. **Needs to be run manually in the Supabase SQL editor** — not applied automatically.

## Still open

**Bad price data from dealeron.** Two vehicles from Stevens Creek Toyota had absurd prices: a 2024 Corolla Hatchback SE at $289, a 2025 Tundra Platinum at $2,624 (both ~100x too low). `dealeron.py` reads price straight from the site's `data-dotagging-item-price` attribute; likely picking up a monthly-payment or incentive figure instead of the actual price on certain promoted vehicles. Not yet root-caused — needs a live look at those specific listing pages.

**No eBay listings ever saved.** `ebay.py` runs in `scraper/main.py`'s marketplace loop but produced zero rows in this export. Could be working-but-finding-nothing, or silently failing (e.g., eBay's markup no longer matches the `s-item__wrapper` selectors, or requests are being blocked). Not yet investigated.

**Most schema columns are never populated**, regardless of source: `mileage`, `seller_type`, `transmission`, `fuel_type`, `description`, `location`, `city`, `posted_at`, `trim` are empty on all 118 rows. None of the three provider scripts extract these fields even where the source site likely exposes them. This blocks the PRD's filter requirements (4.2) and the map/radius search the DB schema already supports.

## Testing recommendation

This investigation only happened because of a manual CSV export. A layered automated approach would catch this class of bug going forward:
1. **Fixture-based unit tests** per provider — save a real HTML/JSON sample from each site, assert `extract_vehicle_data` parses expected fields correctly. Fast, deterministic, no network calls, catches parsing regressions (would have caught the price bug if a fixture with that vehicle's markup existed).
2. **Data sanity checks before save** — price bounds relative to model year, required non-null fields, flag or reject outliers rather than silently writing them. Would have caught the $289 Corolla immediately.
3. **Dedup/upsert correctness test** — assert that saving the same listing twice with the same `original_url` updates rather than inserts a second row.
