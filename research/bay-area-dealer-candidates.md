# Bay Area Dealer Candidates & Platform Research

Candidate franchise dealerships across the [PRD](./prd.md)'s target cities, compiled 2026-07-17 via web search. Scope was deliberately narrowed to franchise dealers in the PRD's named cities (not independent used lots, not a fully exhaustive list — the Bay Area has 150-200+ franchise dealers total).

Updated 2026-07-18: `scraper/main.py` now scrapes 10 dealers — the original 2 (Steven's Creek Toyota on DealerOn, Capitol Honda on DealerInspire) plus 8 more confirmed here and wired into `DEALERS` (2 more DealerOn: Fremont Chevrolet, Fremont Hyundai; 6 more DealerInspire: Capitol Ford, Capitol Chevrolet, Capitol Hyundai, Stevens Creek Hyundai, Sunnyvale Honda, Fremont CDJR). Each was verified with `python main.py --dry-run --max-pages 1` before being added. This list remains the pool to pull further entries from as coverage expands.

Updated 2026-07-20: added an 11th dealer, Lexus Stevens Creek (DealerOn, San Jose) — same auto group as Stevens Creek Toyota, confirmed via a direct `dealeron.scrape()` call (max_pages=1) returning correctly parsed make/model/year/price/mileage/VIN before being added to `DEALERS`.

While verifying, found `dealerinspire.py`'s `page.goto(..., wait_until="networkidle")` timed out on several of these sites (capitolford.com, capitolhyundaisj.com, stevenscreekhyundai.com, sunnyvalehonda.com, fremontcdjr.com) even though they loaded fine in a real browser — some DealerInspire sites run chat widgets/trackers that poll continuously and never let the network go idle. Changed to `wait_until="domcontentloaded"`, since the provider already has an explicit `wait_for_selector(".result-wrap")` right after to confirm real content loaded.

A URL here is **not yet confirmed scrapeable** just by being listed — each site needs its platform identified and (as Capitol Honda showed) a bot-protection check before writing/reusing a provider for it. Update the "Platform" column as each dealer gets verified; strike through ones that turn out unscrapeable (closed, custom site, hard bot-wall, etc).

## Platform vendors identified so far

5 distinct platform vendors confirmed as of 2026-07-17:

| Platform | Signature | Provider |
|---|---|---|
| `dealeron` | `dealeron.js`, `cdn.dlron.us` | [scraper/providers/dealeron.py](../scraper/providers/dealeron.py) |
| `dealerinspire` | `dealerinspire.com` / `dealerteamwork.com` scripts, Cloudflare-gated | [scraper/providers/dealerinspire.py](../scraper/providers/dealerinspire.py) |
| `dealerdotcom` | Cox Automotive Dealer.com — `images.dealer.com`, `pictures.dealer.com`, `/static/ws/inv-listing/` bundle | not built yet |
| `dealereprocess` (DEP) | `cdn.dealereprocess.org` | not built yet |
| `dealersocket-gemini` | `secureoffersites.com`, `_website_gemini` body class | not built yet |

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
| Acura of Fremont | acuraoffremont.com | dealersocket-gemini |
| Fremont Chevrolet | chevroletoffremont.com | dealeron (confirmed, **live in DEALERS**) |
| Fremont Hyundai (DGDG-owned) | fremonthyundai.com | dealeron (confirmed — uses .aspx pages like Stevens Creek Toyota, **live in DEALERS**) |
| Fremont Chrysler Dodge Jeep Ram (DGDG-owned, technically Newark CA) | fremontcdjr.com | dealerinspire (confirmed, **live in DEALERS**) |

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
| Honda of Stevens Creek | hondaofstevenscreek.com | dealerdotcom |
| Stevens Creek BMW | stevenscreekbmw.com | dealerdotcom |
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
