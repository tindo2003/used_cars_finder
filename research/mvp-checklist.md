# MVP Feature Checklist

Checked against [prd.md](./prd.md) (sections referenced in brackets) and the actual codebase as of 2026-07-19. `[x]` = done and verified, `[~]` = partially built, `[ ]` = not started.

**Target audience assumption (2026-07-18):** reprioritized for Bay Area buyers specifically hunting for good deals, not general-purpose car shoppers. This shifts what "MVP" means in a few places. Items unaffected by this framing are left as originally scoped.

**External PRD review (2026-07-19):** independent reviewers gave prioritized feedback on `prd.md`, now incorporated there as a dated addendum plus targeted section edits. Their top-ranked item — defining what a "good deal" actually means — matched this doc's own "Deal-hunter signal" item and was the single highest-priority open decision in the project. **Now built** — see below.

## "Good deal" signal — built and live (2026-07-19)

Was flagged independently by this doc (2026-07-18) and by external PRD review (2026-07-19) as the most important gap: the PRD promises "good deals" throughout, but nothing in the product evaluated deal quality — search and notifications only checked filter-matching. Full parameter rationale and known limitations: [deal-scoring-heuristic.md](./deal-scoring-heuristic.md).

- [x] `scraper/deals.py`: `compute_deal_score()` compares a listing's price against the median of other active listings with the same make/model within ±2 model years and ±20,000 miles, requiring at least 3 comparables to trust the median
- [x] `is_good_deal()` — 12% or more below the comparable median
- [x] `notify_matches` now ranks each digest's top N by deal score (best relative deal first) instead of plain lowest price, falling back to price when a listing can't be scored
- [x] Found and fixed a real bug while verifying live: some listings have `price=0` (a scraper artifact), which produced bogus "100% below median" results — both the target and comparable pool now exclude non-positive prices
- [x] 27 unit tests (`tests/test_deals.py`); 67 backend total passing
- [x] `deal_score`/`is_good_deal` persisted to `listings` (migration 005) via `update_deal_scores()`, run daily as part of `notify.py` — frontend reads the stored value instead of reimplementing the heuristic in TypeScript
- [x] "Good Deal" badge on listing cards, showing the discount percentage — see Listings section below
- [ ] Known limitation, not addressed: no trim-level distinction (e.g. a base F-150 and a Raptor both count as "F-150"), which can produce misleading scores for models with wide trim-driven price spreads
- Full Deal Score / Price History / Days on Market remain explicitly out of scope (per PRD section 8, Future Roadmap) — this was only ever a minimal signal, not the full roadmap item.

## Data ingestion (scraper) — mostly done

- [x] Multi-source scraping: Craigslist + 10 dealer sites (DealerOn, DealerInspire) [2.4]
- [x] Correct dedup/upsert (vin for dealer sources, original_url fallback for VIN-less sources)
- [x] Data quality fixes: dealeron price parsing, mileage/trim/transmission/fuel_type/city/posted_at/seller_type populated
- [x] Dealer display name populated (`dealer_name` on `listings`) — see below, "Source: dealerinspire" fixed
- [x] robots.txt-compliant crawl delays, graceful 403/429 handling
- [x] Scrape/save orchestration extracted into a testable `ScrapeRunner` class (`scraper/runner.py`), separate from `main.py`'s CLI wiring
- [x] Unit tests for the DB layer (`DbClient`, 17 tests) and `ScrapeRunner`
- [ ] **Lower priority for this audience:** Cars.com, Autotrader, Facebook Marketplace connectors [1.1] — more Bay Area *dealer* coverage in existing sources beats a new marketplace *type* for a deal hunter. Keep expanding the dealer list (research/bay-area-dealer-candidates.md) ahead of this.
- [ ] eBay — dropped due to explicit robots.txt prohibition; would need their official Browse API to reinstate
- [ ] **Cross-marketplace duplicate detection** (new, external review 2026-07-19) — the same physical vehicle can appear on Craigslist and a dealer site with no shared identifier (Craigslist often lacks VIN). Distinct from the per-source dedup already built. Flagged as an open decision in `prd.md` section 8, not yet built.
- [ ] Geocoding listings into the `location` PostGIS column (city text is populated, lat/long is not) — needed for radius search [4.2, 5.4]
- [ ] Unit tests for provider parsing logic (dealeron/dealerinspire/craigslist `extract_*` functions) using fixture HTML

## Notification/matching engine — built and verified live end-to-end

- [x] Evaluate every active listing against every active `saved_searches` row (`scraper/notifications.py`) [3.6, 4.6]
- [x] Batched digest emails via Resend — one email per saved search covering its top N new matches (configurable `--notify-top-n`), not one email per listing
- [x] Dedup so the same listing never notifies twice — `notification_history` table, unique `(saved_search_id, listing_id)` constraint, survives crashes/re-runs [4.6]
- [x] Unfiltered ("no criteria set") searches fall back to the N cheapest active listings overall, both in the backend and with a frontend warning before saving such a search
- [x] Verified live: real Resend emails sent for a real saved search, re-run confirmed as 0 duplicate sends
- [x] 17+ unit tests (`tests/test_notifications.py`) covering match logic, batching, and the unfiltered-search fallback
- [x] Notification checking split into its own workflow (`.github/workflows/notify.yml`, `scraper/notify.py`), separate from scraping — lighter (no Playwright), and not delayed by slow scrape runs
- [ ] Browser push notifications — not built (email-only; sufficient for single-user/personal use so far)
- [ ] **Handling of updated listings** (new, external review 2026-07-19) — an already-notified listing never re-triggers even on a material price drop afterward. Not yet decided whether/how to address.
- [ ] **Notification preferences** (new, external review 2026-07-19) — no user-configurable frequency or unsubscribe flow yet.
- **Cadence decision (2026-07-19):** runs once daily, not every 15 min — an explicit user choice to avoid frequent emails, made after discussing the tradeoff against the PRD's "prioritize speed" wording (3.6). This supersedes that PRD line for the current single-user deployment; revisit if this becomes multi-user.

## Auth — not started

- [ ] Sign up / log in — Supabase auth client scaffolding exists (`utils/supabase/{client,server,middleware}.ts`) but no login/signup UI or session handling is wired up [5.1]
- [ ] Persistent user identity (needed for Favorites and true cross-device Saved Searches — both still blocked on this, though Saved Searches now has a no-auth stopgap, see below)

## Search & filters (frontend) — partially built

- [x] Make/model search, min year / max mileage / max price as sliders with sensible bounds [4.1, 4.2]
- [x] Frontend test coverage for search interactions (`app/page.test.tsx`)
- [x] Sorting control [4.3]: Best Deal (default) / Newest / Lowest Price / Highest Price / Lowest Mileage
- [ ] Autocomplete suggestions for make/model [3.3, 4.1]
- [ ] **Lower priority for this audience:** Transmission filter [4.2] and Seller type filter [4.2]
- [ ] Search radius filter [4.2] — blocked on the geocoding gap above

## Listings — partially built

- [x] Listing cards: image, price, year/make/model, mileage, dealer name + city (or a friendly marketplace label) instead of the raw platform code [3.4]
- [x] "Good Deal" badge overlay showing the discount percentage, when `is_good_deal` is true
- [ ] Posting time shown on the card (data exists in the DB, not yet rendered)
- [ ] Dedicated listing detail page: full description, more photos, specs [3.4]

## Saved Searches — mostly built, no-auth stopgap in place

- [x] Create a named saved search (email + filters, including min year / max mileage) [3.5]
- [x] List saved searches created in this browser (tracked via localStorage IDs, not real auth) [4.5]
- [x] Delete a saved search [4.5]
- [ ] Edit / rename an existing saved search [4.5]
- [ ] Enable / disable toggle [4.5]
- [ ] True cross-device sync — blocked on Auth; current localStorage approach is a deliberate, documented stopgap (see `migrations/004_relax_saved_searches_rls_for_client_list_delete.sql` for the accepted RLS tradeoff)

## Favorites — not started (schema-only)

- [x] `favorites` table exists in the DB (`user_id`, `listing_id`, `created_at`)
- [ ] Add/remove favorite UI [3.7, 4.7]
- [ ] Favorites page [3.2]
- Blocked on Auth (needs a real `user_id`) for the PRD's "synced across devices" version — but the Saved Searches localStorage pattern above is a proven template for a no-auth stopgap here too, if wanted before Auth exists.

## Success Metrics — added 2026-07-19 per external review

New PRD section 9 proposes: notification click-through rate (not instrumented), saved searches per user (computable today), indexing latency (partially approximable), retention via `is_active` over time (computable today, but not per-user without auth). See `prd.md` section 9 for detail — this is a proposed starting point, not a committed measurement plan.

## MVP Launch Criteria readout [section 7]

| Criterion | Status |
|---|---|
| Access from any modern browser | ✅ |
| Search aggregated listings | 🟡 partial (make/model/year/mileage/price, 2 source types) |
| Apply filters | 🟡 partial (5 of 6 PRD filters; radius still blocked) |
| Browse results | ✅ |
| Save searches | 🟡 create + list + delete; no edit/enable-disable yet |
| Receive browser/email notifications | 🟡 email done and verified live; browser push not built |
| Open original listing in one click | ✅ |

## Suggested build order (deal-hunter framing, updated 2026-07-19)

1. ~~Decide + implement the "good deal" signal~~ — done, see above.
2. ~~Sorting control + "Good Deal" badge on the frontend~~ — done, see Search & filters / Listings above. Needs migration 005 run in Supabase before "Best Deal" sort/badge show real data.
3. **Cross-marketplace duplicate detection** — even a crude heuristic improves perceived quality as more sources get added.
4. **Auth** — unlocks Favorites, saved-search edit/enable-disable, and true cross-device sync; the Saved Searches localStorage stopgap proves the no-auth pattern works if Auth keeps getting deferred.
5. **Notification gaps** — updated-listing handling and preferences/unsubscribe (e.g. a per-user configurable cadence, now that daily-vs-frequent is a real product decision rather than an assumption).
6. **Remaining filters (transmission, seller type) + listing detail page** — lower priority for this audience than for a general-purpose shopper, but still part of the PRD.
7. **Additional Bay Area dealer coverage + geocoding for radius search** — expand breadth once the core loop is fully tuned. Additional marketplace *types* (Cars.com, Autotrader, Facebook Marketplace) rank below this for a deal-hunter audience.
