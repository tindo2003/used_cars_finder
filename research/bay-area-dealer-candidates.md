# Bay Area Dealer Candidates & Platform Research

Candidate franchise dealerships across the [PRD](./prd.md)'s target cities, compiled 2026-07-17 via web search. Scope was deliberately narrowed to franchise dealers in the PRD's named cities (not independent used lots, not a fully exhaustive list — the Bay Area has 150-200+ franchise dealers total).

Updated 2026-07-18: `scraper/main.py` now scrapes 10 dealers — the original 2 (Steven's Creek Toyota on DealerOn, Capitol Honda on DealerInspire) plus 8 more confirmed here and wired into `DEALERS` (2 more DealerOn: Fremont Chevrolet, Fremont Hyundai; 6 more DealerInspire: Capitol Ford, Capitol Chevrolet, Capitol Hyundai, Stevens Creek Hyundai, Sunnyvale Honda, Fremont CDJR). Each was verified with `python main.py --dry-run --max-pages 1` before being added. This list remains the pool to pull further entries from as coverage expands.

Updated 2026-07-20: added an 11th dealer, Lexus Stevens Creek (DealerOn, San Jose) — same auto group as Stevens Creek Toyota, confirmed via a direct `dealeron.scrape()` call (max_pages=1) returning correctly parsed make/model/year/price/mileage/VIN before being added to `DEALERS`.

Updated 2026-07-19: expanded the Fremont candidate pool via web search — 6 new unverified entries (Premier Nissan of Fremont, Premier Subaru of Fremont, Fremont Mazda, Fremont Buick GMC, Winn Kia of Fremont, Winn Volkswagen). Two of the six (Fremont Mazda, Winn Kia/Winn Volkswagen) are technically in Newark, CA, same as the already-live Fremont CDJR — kept under the Fremont heading since they're part of the same metro cluster and marketed as serving Fremont. Note: a search hit for "Fremont Volkswagen Casper" is a same-named but unrelated dealer group in Casper, WY — not a Bay Area candidate, excluded.

Updated 2026-07-19 (platform-verification pass): all 6 candidates above checked — 2 confirmed `dealeron` (Premier Nissan of Fremont, Fremont Buick GMC), verified live via direct `dealeron.scrape()` calls (63 and 44 vehicles respectively, correct make/model/year/price/mileage/VIN) and **added to `DEALERS`**. The other 4 split across two platforms with no provider built yet: Premier Subaru of Fremont + Fremont Mazda are `dealerdotcom` (Akamai-fronted — same `ddc_diag_akam` diagnostic cookie prefix on both, 403s a bare `curl`; a real provider would need the same kind of bot-protection handling `dealerinspire.py` already needed for Capitol Honda); Winn Kia of Fremont + Winn Volkswagen are `dealersocket-gemini` (same platform already flagged unbuilt for Acura of Fremont — `secureoffersites.com`/`websitegemini`, and notably 406s a plain `curl` request until a real browser-like `Accept` header is sent, which is a header-negotiation quirk, not an actual bot wall).

Updated 2026-07-19 (`dealersocket-gemini` provider built): [scraper/providers/dealersocket_gemini.py](../scraper/providers/dealersocket_gemini.py) added, unlocking Winn Kia of Fremont, Winn Volkswagen, and Acura of Fremont — all 3 verified live (64 vehicles each, correct make/model/trim/year/price/mileage/VIN) and **added to `DEALERS`** (now 16 dealers total). This platform exposes make/model as a single free-text title (e.g. "2003 Honda CR-V LX FWD") with no per-field data attributes — the real per-field breakdown lives in each card's `data-itemid` attribute instead (`Make-Model-Trim-VIN`, hyphen-joined), which is genuinely ambiguous to split naively since both Make (e.g. "Mercedes-Benz") and Model (e.g. "CR-V", "Q4 e-tron") can themselves contain hyphens — `parse_item_id()` pops VIN/Trim off the end first (always reliable) and checks a small known hyphenated-make set before assuming the remainder's first segment alone is the Make; 12 unit tests cover this including both hyphen-ambiguity cases. No mileage issue here (present via a `details-item-row` label/value list, unlike title/data attributes) but transmission/fuel type are absent from the card entirely, same tradeoff `dealerinspire.py` already made. Also hit the identical `networkidle`-hangs-on-chat-widgets issue `dealerinspire.py` fixed (confirmed live on Acura of Fremont specifically) — fixed the same way (`domcontentloaded` + explicit `wait_for_selector`). Pagination is simpler than DealerOn/DealerInspire here: real `?page=N` query-param links, so the provider reads the max page number directly off the first page's pagination list and navigates by URL instead of clicking. Robots.txt (identical template across all 3 confirmed sites) explicitly lists AI-crawler user agents including `ClaudeBot`/`claude-web`/`anthropic-ai` alongside search engines, but its one `Disallow` rule (`/inventory*,*`) only blocks comma-containing faceted-filter URLs, not the plain `/inventory/used[?page=N]` path this provider actually requests — worth knowing given who's doing the requesting here, but not a blocker.

Updated 2026-07-22 (`dealerdotcom` provider built): [scraper/providers/dealerdotcom.py](../scraper/providers/dealerdotcom.py) added, unlocking all 4 of the candidates below at once. Scoped deliberately to Mountain View/Sunnyvale/San Jose/Fremont per an explicit user ask -- investigation found every dealer in those 4 cities matching an already-built provider had already been added in earlier passes; every *remaining* candidate needed either a brand-new provider or had a confirmed hard bot-wall (BMW of Mountain View: navigation itself denied, even via a real browser). `dealerdotcom` was the highest-value remaining target (4 candidates vs. 2 for the unexplored `dealereprocess`).

This platform's Akamai Bot Manager is confirmed *more* aggressive than the Cloudflare gate `dealerinspire.py` already handles: a plain `curl`/HTTP request -- even to `/robots.txt` -- gets an explicit `403` with `set-cookie: ddc_akam_bot=...BOT-BROWSER-IMPERSONATOR...`. A real browser session gets through fine (confirmed live), so the same stealth Playwright launch args `dealerinspire.py` uses (disabling the automation-controlled flag, hiding `navigator.webdriver`, a realistic UA) were reused here too, and worked.

The real discovery, though, was that this platform's used-inventory pages embed a full schema.org `CollectionPage` JSON-LD block (`<script type="application/ld+json">`) whose `about.offers.itemOffered` array is a complete structured record per vehicle -- VIN, brand, model, year, price, transmission, fuel type, photo -- confirmed live against Premier Subaru of Fremont. This is dramatically more reliable than scraping the visible card (which has no VIN anywhere except a slow/inconsistently-loading third-party "privacy4cars" compliance badge, and only a single unstructured title string for make/model, the same ambiguous-parsing problem `dealersocket_gemini.py`'s hyphen-joined `data-itemid` already deals with). `dealerdotcom.py` joins each DOM card to its JSON-LD entry by URL path (the JSON-LD's `url` is absolute and query-free; a card's own `href` is relative and carries a `?priorityType=spv` tracking param, so both get normalized to a bare path before matching) and prefers the JSON-LD for everything except mileage.

**Found and worked around a real data-quality trap in that JSON-LD**: its `mileageFromOdometer.value` is truncated to thousands -- a genuine 32,373-mile vehicle (confirmed against the same card's own rendered "32,373 miles" badge) reports `"value": 32` in the JSON-LD. Silently trusting this field would have written wildly wrong mileage for every vehicle. `dealerdotcom.py` deliberately keeps reading mileage from the card's own rendered highlight badge instead, never from JSON-LD, with a dedicated regression test (`test_extract_vehicle_data_prefers_json_ld_over_card_text`) pinned to this exact real example.

Verified live against all 4 candidates individually before adding any to `DEALERS` (this project's established convention -- never bulk-add on the assumption sibling dealers are identical): Premier Subaru of Fremont (14 vehicles, 0 missing VINs), Fremont Mazda (24 vehicles), Honda of Stevens Creek (24 vehicles), Stevens Creek BMW (24 vehicles) -- all correctly parsed make/model/year/price/VIN, transmission and fuel_type populated from the JSON-LD where DealerInspire/DealerSocket-Gemini can't offer either. 7 new unit tests in `tests/test_dealerdotcom.py`. No documented `Crawl-delay` in this platform's `robots.txt` (confirmed live, readable via a real browser despite curl being blocked) -- a 3-second per-page delay is used regardless, slightly more conservative than `dealersocket_gemini.py`'s 2-second precedent given the more aggressive bot-wall observed here.

Still unbuilt: `dealereprocess` (Fremont Auto Mall, Fremont Toyota) -- completely unexplored, out of scope for this pass (only `dealerdotcom` was requested).

While verifying, found `dealerinspire.py`'s `page.goto(..., wait_until="networkidle")` timed out on several of these sites (capitolford.com, capitolhyundaisj.com, stevenscreekhyundai.com, sunnyvalehonda.com, fremontcdjr.com) even though they loaded fine in a real browser — some DealerInspire sites run chat widgets/trackers that poll continuously and never let the network go idle. Changed to `wait_until="domcontentloaded"`, since the provider already has an explicit `wait_for_selector(".result-wrap")` right after to confirm real content loaded.

A URL here is **not yet confirmed scrapeable** just by being listed — each site needs its platform identified and (as Capitol Honda showed) a bot-protection check before writing/reusing a provider for it. Update the "Platform" column as each dealer gets verified; strike through ones that turn out unscrapeable (closed, custom site, hard bot-wall, etc).

## Platform vendors identified so far

5 distinct platform vendors confirmed as of 2026-07-17:

| Platform | Signature | Provider |
|---|---|---|
| `dealeron` | `dealeron.js`, `cdn.dlron.us` | [scraper/providers/dealeron.py](../scraper/providers/dealeron.py) |
| `dealerinspire` | `dealerinspire.com` / `dealerteamwork.com` scripts, Cloudflare-gated | [scraper/providers/dealerinspire.py](../scraper/providers/dealerinspire.py) |
| `dealerdotcom` | Cox Automotive Dealer.com — `images.dealer.com`, `pictures.dealer.com`, `/static/ws/inv-listing/` bundle | [scraper/providers/dealerdotcom.py](../scraper/providers/dealerdotcom.py) |
| `dealereprocess` (DEP) | `cdn.dealereprocess.org` | not built yet |
| `dealersocket-gemini` | `secureoffersites.com`, `_website_gemini` body class | [scraper/providers/dealersocket_gemini.py](../scraper/providers/dealersocket_gemini.py) |

**Detection method:** load the site, inspect `script[src]` and `link[href]` for the vendor's CDN domain.

**Caveat:** `assets.prod.analytics.dealer.com/pix-aop-auto.js` is a shared OEM analytics pixel that shows up across DealerOn, DealerInspire, and other platforms alike — it is **not** a Dealer.com platform signal by itself. Only trust `images.dealer.com` / `pictures.dealer.com` / `/static/ws/inv-listing/` as genuine Dealer.com signatures.

## Status legend
`?` = not yet checked.

## San Francisco
| Dealer | URL | Platform |
|---|---|---|
| BMW of San Francisco | bmwsf.com | ? |
| Mazda San Francisco | mazdasanfrancisco.com | ? |

## Oakland
| Dealer | URL | Platform |
|---|---|---|
| Autocom Nissan of Oakland | (needs exact domain) | ? |
| Mercedes-Benz of Oakland | mercedesbenzofoakland.com | ? |
| Volkswagen of Oakland | vwoakland.com | ? |
| One Toyota of Oakland | onetoyota.com | ? |

## Berkeley / Albany
| Dealer | URL | Platform |
|---|---|---|
| Toyota of Berkeley | toyotaofberkeley.com | ? |
| Berkeley Honda | berkeleyhonda.com | ? |
| Mini of Berkeley | miniofberkeley.com | ? |
| Weatherford BMW | weatherfordbmw.com | ? |
| Albany Subaru | albanysubaru.com | ? |

## Fremont
| Dealer | URL | Platform |
|---|---|---|
| Fremont Auto Mall (Audi/BMW/Honda/Lexus/Mercedes/Porsche hub) | thefremontautomall.com | dealereprocess (DEP) |
| Fremont Toyota | fremonttoyota.com | dealereprocess (DEP) |
| Acura of Fremont | acuraoffremont.com | dealersocket-gemini (confirmed, 64 vehicles via live `dealersocket_gemini.scrape()` test, **live in DEALERS**) |
| Fremont Chevrolet | chevroletoffremont.com | dealeron (confirmed, **live in DEALERS**) |
| Fremont Hyundai (DGDG-owned) | fremonthyundai.com | dealeron (confirmed — uses .aspx pages like Stevens Creek Toyota, **live in DEALERS**) |
| Fremont Chrysler Dodge Jeep Ram (DGDG-owned, technically Newark CA) | fremontcdjr.com | dealerinspire (confirmed, **live in DEALERS**) |
| Premier Nissan of Fremont | premiernissanoffremont.com | dealeron (confirmed via `cdn.dlron.us`/`dealeron.js` signature + live `dealeron.scrape()` test — 63 vehicles correctly parsed, Crawl-delay: 10, **live in DEALERS**) |
| Premier Subaru of Fremont | premiersubaruoffremont.com | dealerdotcom (confirmed, **live in DEALERS** — see "dealerdotcom provider built" note below) |
| Fremont Mazda (technically Newark CA, same pattern as Fremont CDJR) | fremontmazda.com | dealerdotcom (confirmed via live `dealerdotcom.scrape()` test — 24 vehicles correctly parsed, **live in DEALERS**) |
| Fremont Buick GMC | fremontbuickgmc.com | dealeron (confirmed via `cdn.dlron.us`/`dealeron.js` signature + live `dealeron.scrape()` test — 44 vehicles correctly parsed, Crawl-delay: 10, **live in DEALERS**) |
| Winn Kia of Fremont (technically Newark CA) | winnkiaoffremont.com | dealersocket-gemini (confirmed, 64 vehicles via live `dealersocket_gemini.scrape()` test, **live in DEALERS**) |
| Winn Volkswagen (technically Newark CA, serves Fremont) | winnvw.com | dealersocket-gemini (confirmed, 64 vehicles via live `dealersocket_gemini.scrape()` test, **live in DEALERS**) |

## Palo Alto
| Dealer | URL | Platform |
|---|---|---|
| Mercedes-Benz of Palo Alto | mercedesbenzpaloalto.com | ? |
| Audi Palo Alto | audipaloalto.com | ? |
| Magnussen's Toyota of Palo Alto | (needs exact domain) | ? |

## Mountain View
| Dealer | URL | Platform |
|---|---|---|
| BMW of Mountain View | bmwofmountainview.com | ? |
| Hyundai of Mountain View | (needs exact domain) | ? |

## Sunnyvale
| Dealer | URL | Platform |
|---|---|---|
| Anderson Honda | andersonhonda.com | ? |
| Toyota Sunnyvale | (needs exact domain) | ? |
| Sunnyvale Volkswagen | (needs exact domain) | ? |

## San Jose / Santa Clara (Stevens Creek Auto Row + Capitol Expressway Auto Mall)
| Dealer | URL | Platform |
|---|---|---|
| Stevens Creek Toyota | stevenscreektoyota.com | dealeron (confirmed, already in DEALERS) |
| Lexus Stevens Creek | lexusstevenscreek.com | dealeron (confirmed 2026-07-20 via live `dealeron.scrape()` test, `.srp-inventory` container, robots.txt Crawl-delay: 10 same as Stevens Creek Toyota — same auto group, **live in DEALERS**) |
| Capitol Honda | capitolhonda.com | dealerinspire (confirmed, already in DEALERS) |
| Honda of Stevens Creek | hondaofstevenscreek.com | dealerdotcom (confirmed via live `dealerdotcom.scrape()` test — 24 vehicles correctly parsed, **live in DEALERS**) |
| Stevens Creek BMW | stevenscreekbmw.com | dealerdotcom (confirmed via live `dealerdotcom.scrape()` test — 24 vehicles correctly parsed, **live in DEALERS**) |
| Capitol Ford | capitolford.com | dealerinspire (confirmed — same DGDG/Capitol group as Capitol Honda, **live in DEALERS**) |
| Capitol Chevrolet | capitolchevysj.com | dealerinspire (confirmed, **live in DEALERS**) |
| Capitol Hyundai | **capitolhyundaisj.com** (corrected — capitolhyundai.com does not resolve) | dealerinspire (confirmed, **live in DEALERS**) |
| ~~Capitol Genesis / Genesis of Stevens Creek~~ | genesisofstevenscreek.com redirects to stevenscreekhyundai.com | CLOSED — confirmed dead, not a separate scrapeable dealer |
| Capitol Expressway Auto Mall (directory hub, not a single dealer) | capitolautomall.com | ? |
| Del Grande Dealer Group (parent — many CA brands) | dgdg.com | likely just a directory/hub, not itself scrapeable |
| Sunnyvale Honda (formerly listed as "Larry Hopkins Honda" — larryhopkinshonda.com redirects here) | **sunnyvalehonda.com** (corrected) | dealerinspire (confirmed, **live in DEALERS**) |
| Frontier Ford (Santa Clara) | (needs exact domain) | ? |
| Stevens Creek Hyundai (Santa Clara) | stevenscreekhyundai.com | dealerinspire (confirmed, **live in DEALERS**) |

## Redwood City / San Mateo / San Carlos / Burlingame — Putnam Family Dealerships group
| Dealer | URL | Platform |
|---|---|---|
| Putnam Toyota | putnamtoyota.com | ? |
| Putnam Ford | putnamford.com | ? |
| Putnam Chevrolet | putnamchevy.com | ? |
| Putnam Cadillac | (needs exact domain) | ? |
| Putnam GMC | putnamgmc.com | ? |
| Putnam CJDR (Chrysler/Jeep/Dodge/Ram) | putnam-dodge-chrysler-jeep.com | ? |
| Putnam Kia | (needs exact domain) | ? |
| Putnam Subaru | (needs exact domain) | ? |
| Putnam Mazda | (needs exact domain) | ? |
| Putnam Lexus | (needs exact domain) | ? |
| Honda San Carlos | (needs exact domain) | ? |
| Volvo Cars Burlingame | (needs exact domain) | ? |

## Colma (Serramonte Auto Mall — borders SF/San Mateo)
| Dealer | URL | Platform |
|---|---|---|
| Serramonte Ford | serramonteford.com | ? |
| Honda of Serramonte | hondaofserramonte.com | ? |
| Nissan of Serramonte | nissanofserramonte.com | ? |
| Serramonte Volkswagen | serramontevw.com | ? |
| Serramonte Kia | serramontekia.com | ? |
| Cadillac of South San Francisco | (needs exact domain) | ? |
| Golden State INFINITI | (needs exact domain) | ? |
