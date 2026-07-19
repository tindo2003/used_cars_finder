# Project Memory

A living, high-signal snapshot of this project so a fresh session (any workspace, any machine) can pick up context fast without you re-explaining it. Kept up to date as things change — if something here contradicts the code, the code wins; update this file rather than trust it blindly. Full detail and "why" for everything summarized here lives in `research/` — this file is the index and the current-state snapshot, not a replacement for those docs.

## What this is

**Used Car Finder** — a personal tool (single account, email/password auth as of 2026-07-20) that scrapes used-car listings from Bay Area dealer sites and Craigslist, lets you define saved searches (make/model/year/mileage/price), and emails you a daily digest of new matches, ranked by an actual "good deal" signal rather than just filter-matching. Audience/vision: `research/prd.md`. Full status snapshot with `[x]`/`[ ]` per feature and the suggested build order: `research/mvp-checklist.md` — **read that one first** when picking up work.

## Architecture at a glance

```
scraper/
  main.py            CLI entrypoint for scraping (runs every 15 min via .github/workflows/scraper.yml)
  notify.py           CLI entrypoint for the daily notification check (.github/workflows/notify.yml)
  runner.py           ScrapeRunner -- orchestrates "call a scraper, call the DB saver", testable via fakes
  db.py               DbClient -- generic CRUD over any Supabase table (create/read/update/delete/upsert)
  options.py          ScrapeOptions dataclass -- shared config passed into every provider's scrape()
  notifications.py    matches() + notify_matches() -- saved-search matching, batched digest emails via Resend
  deals.py            compute_deal_score()/is_good_deal()/update_deal_scores() -- the "good deal" heuristic
  duplicates.py        cross-marketplace + same-VIN duplicate detection, writes duplicate_of
  staleness.py         expire_stale_listings() -- marks status="expired" past a configurable last-seen threshold
  utils/              small shared pure-function helpers: pagination.py (page_did_not_advance), timestamps.py (parse_timestamp)
  providers/          craigslist.py, dealeron.py, dealerinspire.py (ebay.py exists but is NOT wired in -- see below)
  tests/              112 tests, fakes.py has a shared in-memory Supabase stand-in with real filter semantics

app/
  page.tsx            The entire frontend (single page): search/filter/sort, listing cards, save-search flow,
                      "My Saved Searches" list+delete, email/password auth (sign up/log in/log out)
  page.test.tsx       28 tests (Vitest + Testing Library)

middleware.ts          root Next.js middleware -- keeps Supabase sessions alive across requests
utils/supabase/         client.ts/server.ts/middleware.ts -- Supabase SSR helpers (see Auth decision below)

migrations/           Run manually in the Supabase SQL editor -- nothing here applies itself
  001  dedupe + fix upsert conflict key (vin for dealer sources, original_url for VIN-less)
  002  notification_history table (dedup for notifications)
  003  dealer_name column on listings
  004  relax RLS so the anon/browser key can select+delete saved_searches (no-auth stopgap, superseded by 010)
  005  deal_score + is_good_deal columns on listings
  006  duplicate_of column on listings (cross-marketplace dedup) -- run 2026-07-20
  007  re-keys dealer-source upsert conflict target from vin alone to (vin, dealer_name) -- run 2026-07-20, fixes the "ghost location" bug (see below); its constraint-name guess for the old constraint was wrong so it only added the new composite constraint (didn't remove the old one) -- see 008
  008  drops the stale listings_vin_unique constraint 007 failed to remove -- run 2026-07-20. Combined 007+008 effect verified live via a synthetic test upsert (two dealer_names sharing one VIN now correctly persist as 2 rows; test rows cleaned up after)
  009  last_seen_at column on listings -- run 2026-07-20
  010  scopes saved_searches RLS to auth.uid() = user_id, replacing migration 004's anon stopgap -- run 2026-07-20, verified live end-to-end (see Auth decision below)
  011  scopes favorites RLS to auth.uid() = user_id + unique index on (user_id, listing_id) -- run 2026-07-20, verified live end-to-end (see Favorites decision below)

.github/workflows/
  scraper.yml         every 15 min, installs Playwright, runs main.py
  notify.yml          once daily (15:00 UTC / 8am Pacific), no Playwright needed, runs notify.py
```

Run tests: `cd scraper && python3 -m pytest tests/ -q` (backend) and `npx vitest run` (frontend, from repo root). Run scraper locally: `cd scraper && python3 main.py --dry-run --max-pages 1` (fast, no DB writes). Local DB access needs `scraper/.env` with `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (service role), `RESEND_API_KEY` -- not committed, gitignored via the `.env*` rule.

## Key decisions already made (don't re-litigate without a reason)

- **eBay is intentionally not scraped.** Its `robots.txt` explicitly disallows the search pattern needed and states automated access is prohibited without permission. `providers/ebay.py` still exists for a possible future pass against their official Browse API, but is not in `main.py`'s `ACTIVE_MARKETPLACES`. Detail: `research/scraping-etiquette.md`.
- **Notifications run once daily, not every 15 min.** Explicit user choice to avoid frequent emails, even though the PRD says "prioritize speed over batching." This supersedes that PRD line for the current single-user deployment. Notification-checking is a separate GitHub Actions workflow from scraping (lighter, no Playwright, not delayed by slow scrapes).
- **Auth: email + password, built 2026-07-20.** Chosen over magic-link specifically because it needs no callback/redirect route -- `signUp`/`signInWithPassword` return a session directly. Requires "Confirm email" disabled in the Supabase dashboard (done) so there's no confirmation-link redirect to handle either. Saved Searches is now scoped to real `user_id` + RLS (migration 010, `auth.uid() = user_id`), replacing the old no-auth localStorage stopgap (migration 004) entirely -- that mechanism is fully removed from the frontend, not just deprecated. Along the way, found and fixed a real gap in the pre-existing Supabase SSR scaffolding: `utils/supabase/middleware.ts` built cookie handlers but never called anything to trigger them, and nothing invoked it from an actual Next.js `middleware.ts` (which didn't exist) -- so sessions would never have persisted across requests. Verified live end-to-end against production: sign-up gives an immediate session, it survives a reload, a saved search is correctly scoped to the account, log-out hides it, log-in restores it; test account and data cleaned up after.
- **Favorites, built 2026-07-20.** RLS scoped the same way (migration 011, `auth.uid() = user_id`, plus a unique index on `(user_id, listing_id)` so a listing can't be favorited twice -- `favorites` predates the migrations/ convention like `saved_searches` did, so its RLS state needed the same explicit treatment migration 010 gave that table). Heart toggle on every card, only shown when logged in; a "My Favorites" section stays a section on the same page rather than a new route, consistent with this app's single-page frontend. Favorited listings fetch in one query via PostgREST's embedded-resource select (`select("*, listings(*)")`) -- confirmed `favorites.listing_id` has a real FK to `listings.id` before relying on this. Verified live end-to-end the same way Auth was: favoriting/un-favoriting a real listing, test account and data cleaned up after.
- **The "good deal" signal is deliberately crude.** Compares a listing's price to the median of other active listings with the same make/model within ±2 model years and ±20,000 miles (needs ≥3 comparables to trust the median); ≥12% below median counts as a deal. No trim-level distinction, no condition/accident history. Full rationale and known limitations: `research/deal-scoring-heuristic.md`.
- **Dedup key is `(vin, dealer_name)` when vin present, `original_url` as fallback** (changed 2026-07-20 from bare `vin` -- see migration 007 and below). This only catches the same ad seen twice from the *same* dealer/source -- **cross-marketplace duplicate detection** (`scraper/duplicates.py`, built 2026-07-20) is the separate pass that catches the same vehicle posted on two different sources with no shared identifier: (a) a dealer's own site plus its own Craigslist repost -- fuzzy match on make/model/model_year + mileage within 500mi + price within $250 across differing `marketplace_source`; (b) an **exact VIN match**, unconditional and bypassing the fuzzy/marketplace_source checks entirely, added after a user-flagged gap -- dealer groups can syndicate the same VIN across sister storefronts (e.g. a trade-in shows up on both "Capitol Honda" and "Capitol Ford"), which used to be invisible: the old bare-`vin` upsert conflict key made the second store's scrape silently overwrite the first store's dealer_name/city/original_url in place, no duplicate row, no history, just a listing that flip-floped location depending on scrape order. Both paths write `duplicate_of` (migration 006) onto the non-canonical row daily via `notify.py`; frontend and `notify_matches` both exclude flagged duplicates. Verified live 2026-07-20: 0 of 740 active listings shared a VIN at that time (risk was latent, not yet manifested, but real given several dealers are sibling stores in the same ownership group).
- **`original_url` can also collide across dealers, not just `vin`.** Found 2026-07-20 from a real production crash: `providers/dealerinspire.py` takes `original_url` verbatim from the card's own `href`, which can point straight to a *different* dealer's site (confirmed live: a Capitol Honda card linking to chevroletoffremont.com -- shared/syndicated inventory). `original_url` has its own table-wide unique constraint independent of `(vin, dealer_name)`, so a new `(vin, dealer_name)` pair can still crash on `original_url` already belonging to someone else's row. `db.upsert()` now catches that specific constraint violation (`_is_original_url_conflict`) and skips the car (returns `None`, tallied in `progress["skipped"]`) rather than overwriting the existing row's identity through a side door. Verified by reproducing the exact crash against production with synthetic data, cleaned up after.
- **Pagination has a stall guard** (`pagination.page_did_not_advance`) after a real bug where "Next" clicks could succeed without the page actually changing, causing the same vehicles to be re-scraped up to hundreds of times in one run. Tested specifically to confirm genuine page-to-page advancing (including partial inventory overlap) is never mistaken for a stall.
- **Stale listings expire after a configurable window (default 90 days) of not being reconfirmed** (`scraper/staleness.py`, built 2026-07-20, user-directed design). `db.py`'s upsert stamps `last_seen_at` on every insert/update; `notify.py` runs `expire_stale_listings()` first (before dup/deal-score/notify steps) each day, marking `status="expired"` on anything past the threshold -- which then falls out of every other read for free (frontend, deals.py, duplicates.py, notifications.py all already filter on `status="active"`). Working assumption (user's, confirmed intentional): a listing the scraper keeps re-seeing is more likely still available than one it hasn't re-seen in months -- this is a proxy for "probably sold," not an actual delisting check (nothing verifies removal from the source). `last_seen_at` is also wired into `deals.ranking_key` and the frontend's listings query as a **tiebreaker only** (most-recently-seen wins ties), never the primary sort -- explicit user choice. **Known asymmetry:** far more reliable for dealer listings (full-inventory re-scrape every 15-min run) than Craigslist (`runner.py` only re-searches make/models with a currently *active* saved search, so a Craigslist listing can go stale just because no one's searching for it, not because it sold) -- user explicitly accepted this as an acceptable outlier rather than building Craigslist-specific compensation.
- **Dealer coverage**: 11 dealers currently in `main.py`'s `DEALERS` list (San Jose/Santa Clara/Sunnyvale/Fremont/Newark cluster; Lexus Stevens Creek added 2026-07-20). More candidates with unverified platforms: `research/bay-area-dealer-candidates.md`.

## Known open items (not yet decided or built)

See `research/mvp-checklist.md`'s "Suggested build order" for the live, prioritized list. As of this writing, next up: **notification gaps** (updated-listing/price-drop re-triggering, per-user preferences/unsubscribe). Also open: saved-search edit/enable-disable, multi-make/multi-model search (`make`/`model` are single-value today on both the search filter and `saved_searches`), several PRD filters (transmission, seller type, radius search -- blocked on geocoding), a listing detail page, additional dealer coverage. All migrations through 011 have been run in Supabase.

## Where to look for more

| Doc | What's in it |
|---|---|
| `research/prd.md` | Product vision, audience, functional requirements -- plus dated addenda for the deal-hunter audience refinement and external review feedback |
| `research/mvp-checklist.md` | **Start here.** Feature-by-feature status vs. the PRD, suggested build order |
| `research/gap-analysis.md` | Earlier snapshot of PRD vs. codebase (2026-07-17, partially superseded by mvp-checklist.md) |
| `research/deal-scoring-heuristic.md` | The "good deal" parameters, rationale, known limitations |
| `research/scraping-etiquette.md` | robots.txt findings per platform, crawl-delay compliance, why eBay is excluded |
| `research/data-quality-findings.md` | Real bugs found and fixed: duplicate rows, dealeron price parsing, pagination stalls, missing fields |
| `research/bay-area-dealer-candidates.md` | Candidate dealers by city, platform verification status, for expanding `DEALERS` |
