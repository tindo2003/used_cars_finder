# "Good Deal" Scoring Heuristic

Documents the heuristic implemented in [`scraper/deals.py`](../scraper/deals.py), built 2026-07-19 in response to the highest-priority gap flagged by both this project's own analysis and external PRD review (see `prd.md`'s addenda and `mvp-checklist.md`): the product promised "good deals" but never evaluated deal quality, only filter-matching.

## What it does

For a given listing, `compute_deal_score()` finds "comparable" listings and returns how far below their median price the listing sits, as a fraction (e.g. `0.15` = 15% below median; negative means priced above median).

## Parameters (chosen 2026-07-19, confirmed with the user before implementing)

| Parameter | Value | Meaning |
|---|---|---|
| `DEAL_YEAR_WINDOW` | 2 | Comparable listings must be within ±2 model years |
| `DEAL_MILEAGE_WINDOW` | 20,000 | Comparable listings must be within ±20,000 miles |
| `DEAL_MIN_COMPARABLES` | 3 | Need at least 3 comparable listings to trust the computed median; otherwise returns `None` (unscoreable, not "not a deal") |
| `DEAL_THRESHOLD` | 0.12 | A listing counts as a "good deal" (`is_good_deal()`) at 12% or more below the comparable median |

A "comparable" listing must also match on **make and model** (case-insensitive exact match — not the fuzzy substring match search filters use, since lumping e.g. "Accord" with "Accord Hybrid" would skew the median toward a different vehicle class).

## Where it's used

`notify_matches()` in `scraper/notifications.py` sorts each digest email's candidate matches by `ranking_key()` — deal score descending (best deal first) — and takes the top N, instead of the previous plain lowest-price sort. Listings that can't be scored (fewer than 3 comparables) are still included, just ranked after every scored listing and ordered by price among themselves — "we can't judge this one" is treated differently from "this one isn't a deal."

Not wired into the frontend yet — no "Good Deal" badge on listing cards. Backend/notification ranking only, per the scope agreed when this was built.

## Known limitations (accepted, not yet addressed)

- **No condition/accident-history signal.** Two otherwise-identical listings might have very different real value due to accident history, which this heuristic has no way to see.
- **Sparse categories get no signal.** Uncommon make/model/year/mileage combinations may never reach 3 comparables, especially early on with limited dealer coverage — those listings simply fall back to price-only ranking. This got a bit more likely after the seller_type fix below (thinner per-channel pools), an accepted tradeoff over silently mixing channels.

## Fixed: private-party vs. dealer distinction (2026-07-20)

Originally flagged 2026-07-20 as "not addressed," then re-flagged the same day with concrete production evidence: a Lexus-grouped notification digest was dominated by very old, very cheap Craigslist listings ($2,900–$6,800) ranked as the best available matches. Root cause: Craigslist listings are overwhelmingly private-party sales, priced meaningfully lower than a dealer's listing of a comparable car (no reconditioning cost, no dealer markup, no warranty backed into the price) — `_is_comparable()` didn't check `seller_type` at all, so these cheap listings got judged against a median pulled down by (or, in a thin dealer pool, isolated among) other similarly cheap private-party listings, making them look like outsized deals purely from being systematically cheaper by channel, not from being unusual values within their own channel.

Fixed by adding a `seller_type` equality check to `_is_comparable()` (case-insensitive, matching the make/model checks). Craigslist never sets `seller_type` (stays `None`), so `None == None` still lets Craigslist listings compare against each other — only cross-channel (dealer vs. private-party) pairs are excluded now. Chose the simpler of the two options this doc previously left open (exclude cross-type entirely vs. same-type-first-with-mixed-fallback): a same-type-only exclusion, accepting that some thin per-channel pools will now fall below `DEAL_MIN_COMPARABLES` and fall back to price-only ranking — consistent with this heuristic's existing philosophy that "can't judge" is handled differently from "not a deal," rather than reintroducing the same cross-channel skew through a fallback path.

## Fixed: trim-level distinction (2026-07-22)

Previously accepted as a limitation ("a base F-150 and a Raptor both count as make=Ford, model=F-150"), with the assumption that trim wasn't consistently scraped enough across sources to use as a comparable-grouping field. **Checked real production data before designing anything**, and that assumption turned out to be outdated: trim is populated for ~99% of dealer listings across all 4 dealer platforms (dealeron, dealerinspire, dealersocket-gemini, dealerdotcom -- the last of these got its own trim-extraction fix in the same pass, since it initially shipped setting `trim: None` unconditionally despite the data being available in its JSON-LD source). Craigslist is the one source with 0% trim (no structured trim field in a Craigslist ad), but Craigslist is only 6.3% of active listings and was already excluded from dealer comparisons by the `seller_type` check above.

**Measured two designs against real listings before picking one** (a local monkeypatch of `_is_comparable`, read-only, no writes):
- A **hard trim-equality requirement** (the same pattern as the `seller_type` check) guts coverage badly: 488→211 of 963 scorable listings (50.7%→21.9%). Trim strings are dealer-specific free text ("XLE Premium 4dr Sedan"-style), not a small clean taxonomy -- exact-string matches are too rare to reliably clear `DEAL_MIN_COMPARABLES` for most make/model/trim combinations.
- A **tiered fallback** -- try a same-trim comparable pool first (`_is_comparable_same_trim()`); if that pool has fewer than `DEAL_MIN_COMPARABLES`, fall back to the existing trim-agnostic pool -- preserves coverage exactly (488 scored, unchanged) while 22% of listings (212/963) now get the stricter, more accurate trim-matched comparison. `is_good_deal` count shifted 93→88, the correct direction: a few previously-flagged "deals" were only deals against the wrong-trim pool.

Shipped the tiered design. Same `None`-vs-`None` treatment as `seller_type`'s existing check: two listings both missing trim still compare against each other (keeps Craigslist-vs-Craigslist and any trim-less dealer listings working), but a listing with a real trim never matches one with none.

## What this is not

This is a deliberately crude, minimal signal — explicitly *not* the full "Deal Score" roadmap item named in `prd.md` section 8 (Future Roadmap), which envisions a more sophisticated model (potentially incorporating trim, condition, accident history, market-wide pricing trends, etc.). That remains out of scope.

## Bug found and fixed while verifying live

Some listings have `price = 0` — a known scraper artifact (certain price-parsing paths default to `0` when a price attribute is missing or unparseable on the source site, e.g. `dealeron.py`'s `data-dotagging-item-price` fallback, or `craigslist.py`'s parse-failure default). Before the fix, a `$0` listing would show as "100% below median," a false positive. Both the target listing and the comparable pool now exclude non-positive prices.
