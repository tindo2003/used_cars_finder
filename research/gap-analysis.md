# Gap Analysis: PRD vs Codebase

Snapshot date: 2026-07-17. Compares [prd.md](./prd.md) against the codebase as it stood on that date. Treat this as a point-in-time snapshot, not living documentation — re-check the actual code before relying on it, and update or delete sections here once the gaps below are closed.

## Built and matching the PRD
- Search by make/model/max price against Supabase (`app/page.tsx`)
- Multi-source listing normalization: `marketplace_source` field; scrapers for Craigslist, eBay, and dealer sites via `scraper/providers/` (DealerOn, DealerInspire)
- "Open Original Listing" redirect pattern already matches PRD section 4.4

## Missing / gaps as of 2026-07-17
- **No auth/accounts.** Saved-search save is just a raw email field per submission — no login, so "synced across devices" (PRD 3.5) and Favorites (needs a persistent user) aren't possible yet.
- **No notification engine.** `scraper/main.py` writes new listings to Supabase but nothing evaluates them against `saved_searches` rows or sends email/browser notifications (PRD 3.6/4.6). This is the retention engine of the whole product per the PRD's own framing, and it's currently a no-op.
- **No Favorites** — no table, no UI (PRD 3.7/4.7).
- **Filters are thin** — PRD wants min year, max mileage, transmission, seller type, radius; only make/model/max price exist today (PRD 4.2).
- **No listing detail page** — PRD wants a dedicated page per listing with full description/specs (PRD 3.4); currently cards-only, straight out to the source.
- **Data sources incomplete** — PRD names Facebook Marketplace, Cars.com, Autotrader, dealership sites; scraper covers Craigslist, eBay (not in PRD's source list), and DealerOn/DealerInspire dealers only.
- **Most listing fields are never populated** — see [data-quality-findings.md](./data-quality-findings.md). `mileage`, `seller_type`, `transmission`, `fuel_type`, `description`, `location`, `city`, `posted_at`, `trim` are empty on every row from every source, so PRD filters beyond make/model/price (4.2) can't work yet even though the schema supports them.

## Resolved since 2026-07-17
- ~~Geo/radius unconfirmed~~ — confirmed 2026-07-18: the `listings` table already has PostGIS enabled (`geography_columns`, `spatial_ref_sys` present) and `location`/`saved_searches.target_location` are geography-typed columns. The DB is ready for radius search; no scraper populates `location` yet (see above).

## Timeline read
Project is roughly at the end of the PRD's "Weeks 2–3" (listing aggregation), with "Week 4" (search UI) partially started. "Week 6" (saved searches & notifications) is the biggest structural piece still fully missing.
