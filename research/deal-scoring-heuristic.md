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

- **No trim-level distinction.** A base F-150 and a Raptor both count as make=Ford, model=F-150, so a wide legitimate trim-driven price spread can look like a bogus deal or overpricing. Fixing this would need trim to be a first-class comparable-grouping field, which isn't consistently scraped across all sources yet.
- **No private-party vs. dealer distinction** (user-flagged, 2026-07-20). Craigslist listings are overwhelmingly private-party sales, which tend to price meaningfully lower than a dealer's listing of a comparable car (no reconditioning cost, no dealer markup/profit margin, no warranty backed into the price). `_is_comparable()` doesn't check `marketplace_source`/`seller_type` at all, so a dealer listing's comparable pool can get pulled down by several lower-priced Craigslist listings of the same make/model/year/mileage (and vice versa) — inflating how good a dealer "deal" looks, or making an ordinarily-priced private-party listing look artificially deep against a dealer-skewed median, depending on which way the mix leans. `seller_type` is already scraped and used for saved-search filtering, but isn't factored into comparable-grouping yet. Not scoped/decided: exclude cross-type comparables entirely (may starve some make/models below `DEAL_MIN_COMPARABLES`), or score against same-type comparables only when there are enough of them, falling back to the mixed pool otherwise.
- **No condition/accident-history signal.** Two otherwise-identical listings might have very different real value due to accident history, which this heuristic has no way to see.
- **Sparse categories get no signal.** Uncommon make/model/year/mileage combinations may never reach 3 comparables, especially early on with limited dealer coverage — those listings simply fall back to price-only ranking.

## What this is not

This is a deliberately crude, minimal signal — explicitly *not* the full "Deal Score" roadmap item named in `prd.md` section 8 (Future Roadmap), which envisions a more sophisticated model (potentially incorporating trim, condition, accident history, market-wide pricing trends, etc.). That remains out of scope.

## Bug found and fixed while verifying live

Some listings have `price = 0` — a known scraper artifact (certain price-parsing paths default to `0` when a price attribute is missing or unparseable on the source site, e.g. `dealeron.py`'s `data-dotagging-item-price` fallback, or `craigslist.py`'s parse-failure default). Before the fix, a `$0` listing would show as "100% below median," a false positive. Both the target listing and the comparable pool now exclude non-positive prices.
