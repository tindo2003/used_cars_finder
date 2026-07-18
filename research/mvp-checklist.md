# MVP Feature Checklist

Checked against [prd.md](./prd.md) (sections referenced in brackets) and the actual codebase as of 2026-07-18. `[x]` = done and verified, `[~]` = partially built, `[ ]` = not started.

**Target audience assumption (2026-07-18):** reprioritized for Bay Area buyers specifically hunting for good deals, not general-purpose car shoppers. This shifts what "MVP" means in a few places — see the "Deal-hunter signal" section and the reordered priorities below. Items unaffected by this framing are left as originally scoped.

## Data ingestion (scraper) — mostly done

- [x] Multi-source scraping: Craigslist + 10 dealer sites (DealerOn, DealerInspire) [2.4]
- [x] Correct dedup/upsert (vin for dealer sources, original_url fallback for VIN-less sources)
- [x] Data quality fixes: dealeron price parsing, mileage/trim/transmission/fuel_type/city/posted_at/seller_type populated
- [x] robots.txt-compliant crawl delays, graceful 403/429 handling
- [x] Unit tests for the DB layer (`DbClient`, 17 tests)
- [ ] **Lower priority for this audience:** Cars.com, Autotrader, Facebook Marketplace connectors [1.1] — for a deal hunter, more Bay Area *dealer* coverage in the sources you already have beats a new marketplace *type*. Keep expanding the dealer list (research/bay-area-dealer-candidates.md) ahead of this.
- [ ] eBay — dropped due to explicit robots.txt prohibition; would need their official Browse API to reinstate
- [ ] Geocoding listings into the `location` PostGIS column (city text is populated, lat/long is not) — needed for radius search [4.2, 5.4]
- [ ] Unit tests for provider parsing logic (dealeron/dealerinspire/craigslist `extract_*` functions) using fixture HTML

## The biggest gap: notification/matching engine — not started

- [ ] Evaluate newly-scraped listings against active `saved_searches` rows [3.6, 4.6]
- [ ] Email notifications
- [ ] Browser push notifications
- [ ] Dedup so the same listing never notifies twice [4.6]

This is the PRD's own framing of the product's core value ("the intelligence layer"), and right now `saved_searches` rows are written but nothing ever reads them back. **For a deal-hunter audience this is even more clearly the #1 priority** — being first to see an underpriced listing before someone else grabs it is the entire pitch; a search UI without this is just a slower version of checking each dealer site manually.

## Deal-hunter signal — not in the original PRD scope, flagging as a decision

The PRD explicitly places "Deal Score" and "Price History" in **Non-Goals (2.5)** and **Future Roadmap (section 8)** — deliberately deferred past MVP. That's a reasonable call for a general-purpose search tool, but for an audience specifically hunting deals, some version of this is arguably closer to the core value proposition than search polish is. Not resolving this unilaterally — flagging it as a scope decision:

- [ ] **Decide:** ship MVP without any deal signal (per original PRD), or pull forward a crude version?
- [ ] If pulled forward: a lightweight "$X below similar listings" comparison (same make/model/year-range/mileage-range, computed from data already being collected) — far short of the full "Deal Score" roadmap item, but usable with what's already in the DB
- [ ] Full Deal Score / Price History / Days on Market remain explicitly out of scope either way (per PRD section 8) — this is only about a minimal version, not building the roadmap item early

## Auth — not started

- [ ] Sign up / log in — Supabase auth client scaffolding exists (`utils/supabase/{client,server,middleware}.ts`) but no login/signup UI or session handling is wired up [5.1]
- [ ] Persistent user identity (needed for Favorites and cross-device Saved Searches — both are blocked on this)

## Search & filters (frontend) — partially built

- [x] Make/model search, max price filter [4.1]
- [ ] **Higher priority:** Sorting, especially Lowest Price — currently only a fixed `posted_at desc` order, no user control [4.3]. For a deal hunter this (or a price/mileage-adjusted variant) is arguably the more natural default than "Newest Listings."
- [ ] **Higher priority:** Min model year filter [4.2] and Max mileage filter [4.2] — both are direct value-per-dollar proxies for a deal hunter
- [ ] Autocomplete suggestions for make/model [3.3, 4.1]
- [ ] **Lower priority for this audience:** Transmission filter [4.2] and Seller type filter [4.2] — personal-preference filters, less central to deal-hunting than price/year/mileage
- [ ] Search radius filter [4.2] — blocked on the geocoding gap above

## Listings — partially built

- [x] Listing cards: image, price, year/make/model, mileage, source [3.4]
- [ ] Location and posting time shown on the card (data now exists in the DB, just not rendered)
- [ ] Dedicated listing detail page: full description, more photos, specs [3.4]

## Saved Searches — partially built

- [x] Create a saved search (email + filters) [3.5]
- [ ] List / view existing saved searches [4.5]
- [ ] Edit / rename [4.5]
- [ ] Enable / disable [4.5]
- [ ] Delete [4.5]
- [ ] Sync across devices — blocked on Auth

## Favorites — not started (schema-only)

- [x] `favorites` table exists in the DB (`user_id`, `listing_id`, `created_at`)
- [ ] Add/remove favorite UI [3.7, 4.7]
- [ ] Favorites page [3.2]
- Blocked on Auth (needs a real `user_id`) for the PRD's "synced across devices" version
- [ ] **Possible shortcut for this audience:** a localStorage-based watchlist (no auth required) trades cross-device sync for speed to ship — a deal hunter wants to bookmark/compare candidates *now*, not after a signup flow. Worth considering as a stopgap ahead of full auth rather than blocking Favorites entirely on it.

## MVP Launch Criteria readout [section 7]

| Criterion | Status |
|---|---|
| Access from any modern browser | ✅ |
| Search aggregated listings | 🟡 partial (make/model/price only, 2 sources) |
| Apply filters | 🟡 partial (3 of 6 PRD filters) |
| Browse results | ✅ |
| Save searches | 🟡 create-only, no management UI |
| Receive browser/email notifications | ❌ not started |
| Open original listing in one click | ✅ |

## Suggested build order (deal-hunter framing)

1. **Notification/matching engine** — even more clearly #1 for this audience: speed to see a new underpriced listing is the entire value prop.
2. **Lowest-price sorting + min-year/max-mileage filters** — cheap to build, directly serves "find good deals" better than the remaining PRD filters do.
3. **Decide on the deal-hunter signal** (see that section) — resolve this before or alongside #2, since it affects how listings are ranked/displayed.
4. **Auth** — still needed for real saved-search management and cross-device Favorites; can be partially deferred if the localStorage Favorites shortcut is taken first.
5. **Saved search management UI + Favorites UI** — straightforward once auth exists (or once the localStorage shortcut is in place for Favorites specifically).
6. **Remaining filters (transmission, seller type) + listing detail page** — lower priority for this audience than for a general-purpose shopper, but still part of the PRD.
7. **Additional Bay Area dealer coverage + geocoding for radius search** — expand breadth once the core loop (search → save → notify) works end to end. Additional marketplace *types* (Cars.com, Autotrader, Facebook Marketplace) rank below this for a deal-hunter audience.
