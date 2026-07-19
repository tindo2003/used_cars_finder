# MVP Feature Checklist

Checked against [prd.md](./prd.md) (sections referenced in brackets) and the actual codebase as of 2026-07-19. `[x]` = done and verified, `[~]` = partially built, `[ ]` = not started.

**Target audience assumption (2026-07-18):** reprioritized for Bay Area buyers specifically hunting for good deals, not general-purpose car shoppers. This shifts what "MVP" means in a few places. Items unaffected by this framing are left as originally scoped.

**External PRD review (2026-07-19):** independent reviewers gave prioritized feedback on `prd.md`, now incorporated there as a dated addendum plus targeted section edits. Their top-ranked item — defining what a "good deal" actually means — matches this doc's own "Deal-hunter signal" item below and is now the single highest-priority open decision in the project. See `prd.md`'s addendum for the full ranking and per-item detail.

## Highest-priority open decision: what does "good deal" mean?

Flagged independently by this doc (2026-07-18) and by external PRD review (2026-07-19) as the most important gap. The PRD promises "good deals" throughout, but nothing in the product actually evaluates deal quality — search and notifications both only check filter-matching (make/model/price/year/mileage/etc.), never whether a price is actually good relative to comparable listings.

- [ ] **Decide:** ship MVP without any deal signal (current state), or implement a crude version now?
- [ ] If implemented: a lightweight "$X below comparable listings" signal — same make/model, similar year/mileage range, price vs. the median of that group, computed from data already in the `listings` table. This would change: (a) how `notifications.py` ranks/selects the "top N" listings per digest (currently plain lowest-price, see below), and (b) potentially a "Good Deal" badge on listing cards.
- [ ] Full Deal Score / Price History / Days on Market remain explicitly out of scope regardless (per PRD section 8, Future Roadmap) — this is only about a minimal signal, not the full roadmap item.

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
- [ ] Browser push notifications — not built (email-only; sufficient for single-user/personal use so far)
- [ ] **Handling of updated listings** (new, external review 2026-07-19) — an already-notified listing never re-triggers even on a material price drop afterward. Not yet decided whether/how to address.
- [ ] **Notification preferences** (new, external review 2026-07-19) — no user-configurable frequency or unsubscribe flow yet.
- [ ] Worst-case latency is one scrape cycle (~15 min via GitHub Actions cron), not truly real-time — acceptable for personal use, noted as a gap against the PRD's "prioritize speed" wording.

## Auth — not started

- [ ] Sign up / log in — Supabase auth client scaffolding exists (`utils/supabase/{client,server,middleware}.ts`) but no login/signup UI or session handling is wired up [5.1]
- [ ] Persistent user identity (needed for Favorites and true cross-device Saved Searches — both still blocked on this, though Saved Searches now has a no-auth stopgap, see below)

## Search & filters (frontend) — partially built

- [x] Make/model search, min year / max mileage / max price as sliders with sensible bounds [4.1, 4.2]
- [x] Frontend test coverage for search interactions (`app/page.test.tsx`)
- [ ] Sorting — still only a fixed `posted_at desc` order, no user-selectable sort control [4.3]. For a deal hunter, Lowest Price (or a deal-adjusted variant, pending the decision above) is a stronger candidate default than Newest Listings.
- [ ] Autocomplete suggestions for make/model [3.3, 4.1]
- [ ] **Lower priority for this audience:** Transmission filter [4.2] and Seller type filter [4.2]
- [ ] Search radius filter [4.2] — blocked on the geocoding gap above

## Listings — partially built

- [x] Listing cards: image, price, year/make/model, mileage, dealer name + city (or a friendly marketplace label) instead of the raw platform code [3.4]
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

1. **Decide + implement the "good deal" signal** — now the single highest-priority open item, per both this doc and external review. Affects notification ranking and potentially listing display.
2. **Sorting control on the frontend** (Lowest Price or deal-adjusted, pending #1) — cheap, high-value for this audience.
3. **Cross-marketplace duplicate detection** — even a crude heuristic improves perceived quality as more sources get added.
4. **Auth** — unlocks Favorites, saved-search edit/enable-disable, and true cross-device sync; the Saved Searches localStorage stopgap proves the no-auth pattern works if Auth keeps getting deferred.
5. **Notification gaps** — updated-listing handling, preferences/unsubscribe, and (optionally) tightening latency below one scrape cycle.
6. **Remaining filters (transmission, seller type) + listing detail page** — lower priority for this audience than for a general-purpose shopper, but still part of the PRD.
7. **Additional Bay Area dealer coverage + geocoding for radius search** — expand breadth once the core loop is fully tuned. Additional marketplace *types* (Cars.com, Autotrader, Facebook Marketplace) rank below this for a deal-hunter audience.
