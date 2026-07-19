# MVP Feature Checklist

Checked against [prd.md](./prd.md) (sections referenced in brackets). Updated as features land — trust the `[x]`/`[ ]` markers and the code over any date in this file. `[x]` = done and verified, `[~]` = partially built, `[ ]` = not started.

**Target audience assumption (2026-07-18):** reprioritized for Bay Area buyers specifically hunting for good deals, not general-purpose car shoppers. This shifts what "MVP" means in a few places. Items unaffected by this framing are left as originally scoped.

## "Good deal" signal — built and live (2026-07-19)

Was flagged independently by this doc (2026-07-18) and by external PRD review (2026-07-19) as the most important gap: the PRD promises "good deals" throughout, but nothing in the product evaluated deal quality — search and notifications only checked filter-matching. Full parameter rationale and known limitations: [deal-scoring-heuristic.md](./deal-scoring-heuristic.md).

- [x] `scraper/deals.py`: `compute_deal_score()` compares a listing's price against the median of other active listings with the same make/model within ±2 model years and ±20,000 miles, requiring at least 3 comparables to trust the median
- [x] `is_good_deal()` — 12% or more below the comparable median
- [x] `notify_matches` now ranks each digest's top N by deal score (best relative deal first) instead of plain lowest price, falling back to price when a listing can't be scored
- [x] Found and fixed a real bug while verifying live: some listings have `price=0` (a scraper artifact), which produced bogus "100% below median" results — both the target and comparable pool now exclude non-positive prices
- [x] 27 unit tests (`tests/test_deals.py`)
- [x] `deal_score`/`is_good_deal` persisted to `listings` (migration 005) via `update_deal_scores()`, run daily as part of `notify.py` — frontend reads the stored value instead of reimplementing the heuristic in TypeScript
- [x] "Good Deal" badge on listing cards, showing the discount percentage — see Listings section below
- [ ] Known limitation, not addressed: no trim-level distinction (e.g. a base F-150 and a Raptor both count as "F-150"), which can produce misleading scores for models with wide trim-driven price spreads
- Full Deal Score / Price History / Days on Market remain explicitly out of scope (per PRD section 8, Future Roadmap) — this was only ever a minimal signal, not the full roadmap item.

## Data ingestion (scraper) — mostly done

- [x] Multi-source scraping: Craigslist + 11 dealer sites (DealerOn, DealerInspire) [2.4]
- [x] Correct dedup/upsert (vin for dealer sources, original_url fallback for VIN-less sources)
- [x] Data quality fixes: dealeron price parsing, mileage/trim/transmission/fuel_type/city/posted_at/seller_type populated
- [x] Dealer display name populated (`dealer_name` on `listings`) — see below, "Source: dealerinspire" fixed
- [x] robots.txt-compliant crawl delays, graceful 403/429 handling
- [x] Scrape/save orchestration extracted into a testable `ScrapeRunner` class (`scraper/runner.py`), separate from `main.py`'s CLI wiring
- [x] Unit tests for the DB layer (`DbClient`, 17 tests) and `ScrapeRunner`
- [ ] **Lower priority for this audience:** Cars.com, Autotrader, Facebook Marketplace connectors [1.1] — more Bay Area *dealer* coverage in existing sources beats a new marketplace *type* for a deal hunter. Keep expanding the dealer list (research/bay-area-dealer-candidates.md) ahead of this.
- [ ] eBay — dropped due to explicit robots.txt prohibition; would need their official Browse API to reinstate
- [x] **Cross-marketplace duplicate detection** — built 2026-07-20, see `scraper/duplicates.py`. Groups active listings that share make/model/model_year, mileage within 500 miles, and price within $250 across *different* `marketplace_source` values (same-source dupes are already handled by the vin/original_url upsert key). Canonical pick prefers a VIN'd listing (more reliable identity) over a VIN-less repost, tie-broken by earliest `created_at`. Writes `duplicate_of` (migration 006, **run in Supabase 2026-07-20, confirmed live**) onto every active listing, recomputed daily in `notify.py` alongside deal scores. Frontend excludes `duplicate_of is not null` rows from search results; `notify_matches` excludes them from digests too, so the same physical vehicle can't get emailed twice under two rows. Known limitation: the fuzzy make/model/year/mileage/price match is a same-day snapshot heuristic — a stale Craigslist repost with a since-changed price could stop matching and both copies would show up again; not addressed.
- [x] **Same-VIN-different-storefront duplicate detection** — added 2026-07-20 after a user-flagged gap: dealer groups can syndicate one VIN across multiple storefronts they own (e.g. a trade-in shows up on both "Capitol Honda" and sister store "Capitol Ford"), which the marketplace-source-based check above can't see because it's the *same* platform/source. Worse, `scraper/db.py`'s old `on_conflict="vin"` upsert made the second store's scrape silently overwrite the first store's dealer_name/city/original_url in place — no visible duplicate row, no history, just a listing that flip-flops location. Fixed by keying dealer-source upserts on `(vin, dealer_name)` instead so each storefront's listing survives as its own row, plus an unconditional exact-VIN-match rule in `duplicates.py` (bypasses the marketplace_source/fuzzy-tolerance checks entirely — VIN equality is certain, not fuzzy). Took 3 migrations to land cleanly: 007 added the new composite constraint but guessed the wrong name for the old vin-only constraint to drop (`listings_vin_key` vs. the actual `listings_vin_unique`), so it silently no-op'd; 008 dropped the correct one. Both confirmed via a live synthetic-row test (insert two dealers sharing a VIN → 2 rows persist; re-upsert the same vin+dealer_name → updates in place; test rows cleaned up after). Verified against live production data beforehand: 0 of 740 active listings shared a VIN at the time, so this hadn't manifested yet, but several existing/candidate dealers are sibling stores in the same ownership group, so the risk was real and the old design would never have surfaced it. 23 tests across `tests/test_duplicates.py` + `tests/test_db.py`.
- [x] **Exact insert-vs-update reporting per scrape run** — `db.py`'s `upsert()` returns whether it inserted or updated (read off the same response it already gets back, no extra round trip: Postgres only re-applies `created_at`'s default on INSERT). `main.py`'s summary line reports the real split (e.g. "12 new, 582 already existed") instead of an unquantified "most are re-confirming existing rows."
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
- [x] **Stale-listing expiry + recency tiebreak** — built 2026-07-20. `scraper/db.py`'s upsert now stamps `last_seen_at` on every insert/update; `scraper/staleness.py`'s `expire_stale_listings()` (run first in `notify.py`, before dup/deal-score/notify steps) marks `status="expired"` on any active listing not reconfirmed within a configurable window (`--stale-threshold-days`, default 90 days), which then falls out of every downstream read for free since they all already filter on `status="active"`. Working assumption: a listing the scraper keeps re-seeing is more likely still available than one it hasn't re-seen in months. `deals.ranking_key` (used by notification ranking) and the frontend's listings query both use `last_seen_at` as a tiebreaker only (most-recently-seen first), never the primary sort. **Caveat, documented in `staleness.py`'s docstring:** this is a much stronger signal for dealer listings (full-inventory re-scrape every run) than Craigslist (only re-searched for make/models with a currently active saved search — a Craigslist listing can go stale just because no one's searching for it anymore, not because it sold). Migration 009 (`last_seen_at` column) run in Supabase. 22 new tests across `tests/test_timestamps.py`, `tests/test_staleness.py`, `tests/test_deals.py`, `tests/test_db.py`.
- [ ] Browser push notifications — not built (email-only; sufficient for single-user/personal use so far)
- [ ] **Handling of updated listings** (new, external review 2026-07-19) — an already-notified listing never re-triggers even on a material price drop afterward. Not yet decided whether/how to address.
- [ ] **Notification preferences** (new, external review 2026-07-19) — no user-configurable frequency or unsubscribe flow yet.
- **Cadence decision (2026-07-19):** runs once daily, not every 15 min — an explicit user choice to avoid frequent emails, made after discussing the tradeoff against the PRD's "prioritize speed" wording (3.6). This supersedes that PRD line for the current single-user deployment; revisit if this becomes multi-user.

## Auth — built and verified live (2026-07-20)

- [x] Sign up / log in — email + password, built on the existing Supabase auth scaffolding (`utils/supabase/{client,server,middleware}.ts`). Fixed a real gap in that scaffolding along the way: `middleware.ts`'s cookie handlers were never actually triggered (nothing called `getUser()`), and there was no root `middleware.ts` invoking it at all — sessions would never have persisted across requests. Both fixed. "Confirm email" disabled in the Supabase dashboard (manual step) so sign-up returns a session immediately, no callback route needed [5.1]
- [x] Persistent user identity — `saved_searches` re-scoped from the no-auth localStorage stopgap to real `user_id` + RLS (migration 010, `auth.uid() = user_id`), replacing migration 004's anon-key policies entirely. The localStorage ID-tracking mechanism is fully removed from the frontend. Favorites (schema-only, still no UI) is now unblocked for a fast follow-up.
- [x] Verified live end-to-end against production: sign-up → immediate session → persists across reload → saved search scoped to the account → survives log-out/log-in → test account and data cleaned up after.
- [x] 6 new frontend tests for auth; backend suite unaffected.
- [ ] Not built: password reset flow, OAuth providers — not needed for personal/single-user use so far.

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
- [x] "Updated X ago" on each card, from `last_seen_at` (the scraper's last reconfirmation) — same formatting mirrored in the notification digest email (`scraper/notifications.py`), including the dealer name/city instead of the raw `marketplace_source` code there too
- [ ] `posted_at` (the source site's own listing date, different from `last_seen_at` above) not yet shown on the card, though the data exists
- [ ] Dedicated listing detail page: full description, more photos, specs [3.4]

## Saved Searches — real auth now, cross-device sync works

- [x] Create a named saved search (email + filters, including min year / max mileage) [3.5]
- [x] List saved searches for the logged-in account, scoped by real `user_id` + RLS (migration 010) — the localStorage-tracking stopgap is gone [4.5]
- [x] Delete a saved search [4.5]
- [x] True cross-device sync — unblocked by Auth (2026-07-20); log in from any device, same searches
- [ ] Edit / rename an existing saved search [4.5]
- [ ] Enable / disable toggle [4.5]

## Favorites — built and verified live (2026-07-20)

- [x] `favorites` table exists in the DB (`user_id`, `listing_id`, `created_at`); RLS scoped to `auth.uid() = user_id` (migration 011), plus a unique index on `(user_id, listing_id)` so a listing can't be favorited twice [3.7, 4.7]
- [x] Add/remove favorite UI — heart toggle on every listing card, only shown when logged in
- [x] Favorites view — a "My Favorites" section on the same page (not a separate route, consistent with the single-page frontend), listing favorited cars via one embedded query (`select("*, listings(*)")`) rather than a second round trip [3.2]
- [x] Verified live end-to-end: favoriting surfaces a listing in My Favorites immediately, un-favoriting removes it from both places, heart button absent when logged out.
- [x] 6 new frontend tests

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

1. ~~Decide + implement the "good deal" signal~~ — done, see "Good deal" signal above.
2. ~~Sorting control + "Good Deal" badge on the frontend~~ — done, see Search & filters / Listings above.
3. ~~Cross-marketplace duplicate detection~~ (including same-VIN-different-storefront) — done, see Data ingestion above.
4. ~~Auth~~ — done, see Auth above.
5. ~~Favorites UI~~ — done, see Favorites above.
6. **Notification gaps** — updated-listing handling and preferences/unsubscribe (e.g. a per-user configurable cadence, now that daily-vs-frequent is a real product decision rather than an assumption).
7. **Remaining filters (transmission, seller type) + listing detail page** — lower priority for this audience than for a general-purpose shopper, but still part of the PRD.
8. **Additional Bay Area dealer coverage + geocoding for radius search** — expand breadth once the core loop is fully tuned. Additional marketplace *types* (Cars.com, Autotrader, Facebook Marketplace) rank below this for a deal-hunter audience.
