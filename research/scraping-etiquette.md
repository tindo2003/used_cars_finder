# Scraping Etiquette / robots.txt Audit

Audited 2026-07-18 to reduce IP-ban risk and confirm the scraper is behaving well toward every site it touches.

## Findings by source

**eBay — explicit prohibition, not just a ban risk.** `ebay.com/robots.txt` disallows the exact URL pattern `ebay.py` uses: `Disallow: /sch/i.html?_nkw=` and `Disallow: /sch/*_sacat=` both match our request (`/sch/i.html?_nkw=...&_sacat=6001`). The file also states outright: *"The use of robots or other automated means to access the eBay site without the express permission of eBay is strictly prohibited."* The 403s seen while investigating the "zero eBay listings" issue are very likely eBay enforcing exactly this rule, not a generic bot-detection false positive. **Not building a workaround for this** — the compliant path is eBay's official Browse/Finding API, or dropping eBay from `active_marketplaces` in `main.py` until that's in place. See the (still open) eBay zero-results item.

**Craigslist — technically permitted by robots.txt, but ToS still says no bots.** `craigslist.org/robots.txt` doesn't disallow `/search/` (the path `craigslist.py` uses) and sets no `Crawl-delay`. Craigslist's general Terms of Use separately prohibit automated access, which robots.txt doesn't capture — worth being aware of even though it's less clear-cut than eBay's explicit block.

**DealerOn sites — `Crawl-delay: 10`.** Confirmed on stevenscreektoyota.com and fremonthyundai.com (same platform template, so assumed consistent across the DealerOn dealers). `/searchused.aspx` itself isn't disallowed. Our pagination loop was only waiting ~2-3s between "Next" clicks — a real violation of the site's stated preference.

**DealerInspire sites — `Crawl-delay: 1`.** Confirmed on capitolhonda.com and capitolford.com. `/used-vehicles/` isn't disallowed. Our existing 2s wait between pages already satisfies this.

**dealersocket-gemini sites — no `Crawl-delay`, but explicitly names AI-crawler user agents.** Confirmed identical robots.txt template on all 3 dealers on this platform (Acura of Fremont, Winn Kia of Fremont, Winn Volkswagen), added 2026-07-19. Groups `ClaudeBot`, `claude-web`, and `anthropic-ai` alongside Googlebot/Bingbot/GPTBot/PerplexityBot etc. under one rule set — worth flagging given who's doing the requesting here, though the actual rule (`Disallow: /inventory*,*`) only blocks comma-containing faceted-filter URLs (e.g. multi-value filter combinations), not the plain `/inventory/used[?page=N]` path `dealersocket_gemini.py` requests, which is separately `Allow`-listed (`Allow: /*?page=*`). No `Crawl-delay` specified; the provider uses a flat 2s wait between pages, matching DealerInspire's already-compliant cadence, since there's no stated minimum to honor.

## Fixes applied

- `dealeron.py`: bumped the wait after each "Next" click from 2s to 10s to honor `Crawl-delay: 10`.
- `craigslist.py` / `ebay.py`: explicit handling for 403/429 responses (clear log message + clean return instead of silently doing nothing), and jittered the closing delay (2-4s random instead of a fixed 2s) so repeated calls across saved searches don't hit at a perfectly uniform, bot-like cadence.
- DealerInspire and the existing 5-10s random delay between different dealer domains in `main.py` were already compliant — no change needed there.

## Resolved

Removed `ebay.scrape` from `main.py`'s `active_marketplaces` given the explicit robots.txt prohibition above (user decision, 2026-07-18). `scraper/providers/ebay.py` still exists — untouched — in case a future pass wires it up against eBay's official Browse/Finding API instead of HTML scraping.
