# Scraper Data Quality Findings

Found 2026-07-18 by exporting `listings` to CSV and inspecting it directly (118 rows: 86 dealerinspire / Capitol Honda, 20 craigslist, 12 dealeron / Stevens Creek Toyota, 0 eBay).

## Fixed

**Duplicate rows from non-VIN sources (critical, actively growing).** 18 of the 20 craigslist rows were re-inserts of just 5 unique listings — the same `original_url` appearing 3-4 times with different `id`/`created_at`. Root cause: `scraper/main.py`'s `save_cars_to_db` upserted with `on_conflict="vin"`, but craigslist/eBay listings never have a VIN, and Postgres never treats two `NULL`s as conflicting — so every scrape run inserted a fresh duplicate instead of updating. This would keep growing unbounded on every cron run.

Related latent bug: `dealeron.py` and `dealerinspire.py` defaulted missing VINs to the literal string `"Unknown"` rather than `None`. If two vehicles on the same dealer site ever both lacked a VIN, they'd collide under `on_conflict="vin"` and silently overwrite each other.

Fix applied:
- `scraper/main.py`: upsert conflict target changed from `vin` to `original_url` (always `NOT NULL`, unique per listing across every source seen so far).
- `dealeron.py` / `dealerinspire.py`: missing VIN now stored as `None` instead of `"Unknown"`.
- `migrations/001_dedupe_listings_and_fix_conflict_key.sql`: one-time cleanup of existing duplicates + adds the unique constraint on `original_url` the new upsert relies on. **Needs to be run manually in the Supabase SQL editor** — not applied automatically.

**Bad price data from dealeron.** Two vehicles from Stevens Creek Toyota showed different wrong prices on every scrape: the Corolla Hatchback SE (VIN JTND4MBE1R3228151) went $289 → $23,505 → $66,675 across three runs; the Tundra Platinum (VIN 5TFNA5DB0SX249078) went $2,624 → $66,675 → similar drift. Root cause: `dealeron.py` read price from `data-dotagging-item-price`, a third-party analytics tag that is simply unreliable and drifts between page loads — it is not the site's actual displayed price. The real price lives in `data-pricelib`, a base64-encoded string (`"Selling Price:25888.0;...;calc_INTERNET PRICE:25973.0;..."`) that decodes to the same "Internet Price" shown on the vehicle's own detail page. Confirmed live: Corolla's real price is $25,973, Tundra's is $57,973.

Fix applied: `dealeron.py`'s `extract_price` now decodes `data-pricelib` and reads `calc_INTERNET PRICE` (falling back to `Selling Price`, then to the old analytics tag only if `data-pricelib` is missing/unparseable). Verified against the live site with `max_pages=1` — both vehicles now return their correct price.

Also added a `max_pages` parameter to both `dealeron.scrape()` and `dealerinspire.scrape()` (plumbed through `main.py`'s new `--max-pages` CLI flag), so testing a fix no longer requires paginating through the full ~370-vehicle inventory — `python main.py --dry-run --max-pages 1` checks just the first page.

## Still open

**No eBay listings ever saved.** `ebay.py` runs in `scraper/main.py`'s marketplace loop but produced zero rows in this export. Could be working-but-finding-nothing, or silently failing (e.g., eBay's markup no longer matches the `s-item__wrapper` selectors, or requests are being blocked). Not yet investigated.

**Most schema columns are never populated**, regardless of source: `mileage`, `seller_type`, `transmission`, `fuel_type`, `description`, `location`, `city`, `posted_at`, `trim` are empty on all 118 rows. None of the three provider scripts extract these fields even where the source site likely exposes them. This blocks the PRD's filter requirements (4.2) and the map/radius search the DB schema already supports.

## Testing recommendation

This investigation only happened because of a manual CSV export. A layered automated approach would catch this class of bug going forward:
1. **Fixture-based unit tests** per provider — save a real HTML/JSON sample from each site, assert `extract_vehicle_data` parses expected fields correctly. Fast, deterministic, no network calls, catches parsing regressions (would have caught the price bug if a fixture with that vehicle's markup existed).
2. **Data sanity checks before save** — price bounds relative to model year, required non-null fields, flag or reject outliers rather than silently writing them. Would have caught the $289 Corolla immediately.
3. **Dedup/upsert correctness test** — assert that saving the same listing twice with the same `original_url` updates rather than inserts a second row.
