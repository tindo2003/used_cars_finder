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

**Provider signatures refactored to a shared `ScrapeOptions` dataclass.** Every `scrape()` call was growing its own ad-hoc positional argument list (`make, model, max_price, max_pages, ...`), which meant touching every provider's signature and every call site each time a new filter/option was needed. `scraper/options.py` now defines `ScrapeOptions(make, model, max_price, max_pages)`; all four providers (`dealeron`, `dealerinspire`, `craigslist`, `ebay`) take a single `options: ScrapeOptions` argument instead. Future flags (mileage, transmission, radius, etc.) just add a field to `ScrapeOptions` with a default — no provider signatures need to change.

**Most schema columns were never populated (2026-07-18).** `mileage`, `seller_type`, `transmission`, `fuel_type`, `description`, `location`, `city`, `posted_at`, `trim` were empty on every row from every source. Investigated what each source actually exposes at the search-results/list level (deliberately not visiting each vehicle's own detail page, since that would multiply scrape time per vehicle across ~10 dealers):

- **dealeron** (Stevens Creek Toyota, Fremont Chevrolet, Fremont Hyundai): the card's own data attributes are rich — added `trim` (`data-trim`), `mileage` (`data-odometer`), `transmission` (`data-trans`), `fuel_type` (`data-fueltype`), `posted_at` (`data-dotagging-item-inventory-date`), and a constant `seller_type: "dealer"`.
- **dealerinspire** (Capitol Honda/Ford/Chevrolet/Hyundai, Stevens Creek Hyundai, Sunnyvale Honda, Fremont CDJR): the `data-vehicle` JSON blob and rendered card HTML have `trim` and `fueltype` but genuinely **no mileage or transmission anywhere in the list view** — confirmed by dumping the full card `innerHTML`, the `vehicle-details` list is empty in grid view. Added `trim`, `fuel_type`, `posted_at` (`date_in_stock`), `seller_type: "dealer"`. Mileage/transmission remain null for this platform — would require an extra page load per vehicle to get from the detail page.
- **craigslist**: search results carry a `<div class="location">` (e.g. "fairfield / vacaville") — added as `city`. Checked whether listings expose an owner/dealer flag in this markup before assuming one; they don't, so `seller_type` is intentionally left null here rather than guessed.
- **city** for dealer sources comes from a new `city` field on each entry in `main.py`'s `DEALERS` list, threaded through via `ScrapeOptions.city` (added to the dataclass — this is exactly the extensibility it was built for).
- **Not populated for any source**: `description` (only on each listing's own detail page) and the PostGIS `location` (lat/long — would need geocoding a city name or per-listing address, not attempted here).

**No eBay listings ever saved.** Root cause found while checking eBay's list-level markup for a location field: `https://www.ebay.com/sch/i.html` now returns **HTTP 403** to this scraper's request (confirmed directly, not merely "0 results"), so `ebay.py`'s `if res.status_code != 200: return results` silently exits every time. Likely eBay is blocking the request (missing headers/cookies, or outright bot-blocking), not a markup change. Not yet fixed.

## Testing recommendation

This investigation only happened because of a manual CSV export. A layered automated approach would catch this class of bug going forward:
1. **Fixture-based unit tests** per provider — save a real HTML/JSON sample from each site, assert `extract_vehicle_data` parses expected fields correctly. Fast, deterministic, no network calls, catches parsing regressions (would have caught the price bug if a fixture with that vehicle's markup existed).
2. **Data sanity checks before save** — price bounds relative to model year, required non-null fields, flag or reject outliers rather than silently writing them. Would have caught the $289 Corolla immediately.
3. **Dedup/upsert correctness test** — assert that saving the same listing twice with the same `original_url` updates rather than inserts a second row.
