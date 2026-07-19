# Project Memory

A living, high-signal snapshot of this project so a fresh session (any workspace, any machine) can pick up context fast without you re-explaining it. Kept up to date as things change — if something here contradicts the code, the code wins; update this file rather than trust it blindly. Full detail and "why" for everything summarized here lives in `research/` — this file is the index and the current-state snapshot, not a replacement for those docs.

## What this is

**Used Car Finder** — a personal (single-user, no auth) tool that scrapes used-car listings from Bay Area dealer sites and Craigslist, lets you define saved searches (make/model/year/mileage/price), and emails you a daily digest of new matches, ranked by an actual "good deal" signal rather than just filter-matching. Audience/vision: `research/prd.md`. Full status snapshot with `[x]`/`[ ]` per feature and the suggested build order: `research/mvp-checklist.md` — **read that one first** when picking up work.

## Architecture at a glance

```
scraper/
  main.py            CLI entrypoint for scraping (runs every 15 min via .github/workflows/scraper.yml)
  notify.py           CLI entrypoint for the daily notification check (.github/workflows/notify.yml)
  runner.py           ScrapeRunner -- orchestrates "call a scraper, call the DB saver", testable via fakes
  db.py               DbClient -- generic CRUD over any Supabase table (create/read/update/delete/upsert)
  options.py          ScrapeOptions dataclass -- shared config passed into every provider's scrape()
  pagination.py       page_did_not_advance() -- pure function, detects a stalled "Next" click
  notifications.py    matches() + notify_matches() -- saved-search matching, batched digest emails via Resend
  deals.py            compute_deal_score()/is_good_deal()/update_deal_scores() -- the "good deal" heuristic
  providers/          craigslist.py, dealeron.py, dealerinspire.py (ebay.py exists but is NOT wired in -- see below)
  tests/              73 tests, fakes.py has a shared in-memory Supabase stand-in with real filter semantics

app/
  page.tsx            The entire frontend (single page): search/filter/sort, listing cards, save-search flow,
                      "My Saved Searches" list+delete (localStorage-tracked, no auth)
  page.test.tsx       22 tests (Vitest + Testing Library)

migrations/           Run manually in the Supabase SQL editor -- nothing here applies itself
  001  dedupe + fix upsert conflict key (vin for dealer sources, original_url for VIN-less)
  002  notification_history table (dedup for notifications)
  003  dealer_name column on listings
  004  relax RLS so the anon/browser key can select+delete saved_searches (no-auth stopgap)
  005  deal_score + is_good_deal columns on listings

.github/workflows/
  scraper.yml         every 15 min, installs Playwright, runs main.py
  notify.yml          once daily (15:00 UTC / 8am Pacific), no Playwright needed, runs notify.py
```

Run tests: `cd scraper && python3 -m pytest tests/ -q` (backend) and `npx vitest run` (frontend, from repo root). Run scraper locally: `cd scraper && python3 main.py --dry-run --max-pages 1` (fast, no DB writes). Local DB access needs `scraper/.env` with `SUPABASE_URL`, `SUPABASE_SECRET_KEY` (service role), `RESEND_API_KEY` -- not committed, gitignored via the `.env*` rule.

## Key decisions already made (don't re-litigate without a reason)

- **eBay is intentionally not scraped.** Its `robots.txt` explicitly disallows the search pattern needed and states automated access is prohibited without permission. `providers/ebay.py` still exists for a possible future pass against their official Browse API, but is not in `main.py`'s `ACTIVE_MARKETPLACES`. Detail: `research/scraping-etiquette.md`.
- **Notifications run once daily, not every 15 min.** Explicit user choice to avoid frequent emails, even though the PRD says "prioritize speed over batching." This supersedes that PRD line for the current single-user deployment. Notification-checking is a separate GitHub Actions workflow from scraping (lighter, no Playwright, not delayed by slow scrapes).
- **No auth yet.** Saved Searches has a no-auth stopgap: IDs of searches created in a given browser are tracked in `localStorage`, and RLS was deliberately relaxed (migration 004) so that browser can list/delete its own searches via the anon key. This is a real, accepted tradeoff (any row is technically readable/deletable by anyone calling the API directly), documented in migration 004's comment and `research/mvp-checklist.md`.
- **The "good deal" signal is deliberately crude.** Compares a listing's price to the median of other active listings with the same make/model within ±2 model years and ±20,000 miles (needs ≥3 comparables to trust the median); ≥12% below median counts as a deal. No trim-level distinction, no condition/accident history. Full rationale and known limitations: `research/deal-scoring-heuristic.md`.
- **Dedup key is `vin` when present, `original_url` as fallback** (not always `vin` -- that was a real bug that crashed production once; see `research/data-quality-findings.md`).
- **Pagination has a stall guard** (`pagination.page_did_not_advance`) after a real bug where "Next" clicks could succeed without the page actually changing, causing the same vehicles to be re-scraped up to hundreds of times in one run. Tested specifically to confirm genuine page-to-page advancing (including partial inventory overlap) is never mistaken for a stall.
- **Dealer coverage**: 10 dealers currently in `main.py`'s `DEALERS` list (San Jose/Santa Clara/Sunnyvale/Fremont/Newark cluster). More candidates with unverified platforms: `research/bay-area-dealer-candidates.md`.

## Known open items (not yet decided or built)

See `research/mvp-checklist.md`'s "Suggested build order" for the live, prioritized list. As of this writing, next up: cross-marketplace duplicate detection (same car listed on Craigslist and a dealer site with no shared ID) vs. Auth (unlocks Favorites, saved-search edit/enable-disable, true cross-device sync). Also open: handling of updated listings (price drops on already-notified listings never re-trigger), notification preferences/unsubscribe, browser push notifications, several PRD filters (transmission, seller type, radius search -- blocked on geocoding).

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
