import re
import random
import requests
from bs4 import BeautifulSoup
import time
from typing import Any, Dict, List

from options import ScrapeOptions

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Craigslist search-result pricing is unreliable: syndicated dealer ads
# sometimes show a monthly payment (observed: $302-$420) or a lazy "$0"
# placeholder instead of a real price. Either one would otherwise look
# like an amazing "deal" once ranked, since deal-scoring falls back to
# lowest price when there aren't enough comparables (see deals.py). A
# real used car is never realistically sold for less than this, so
# treat anything under it as bad source data.
MIN_PLAUSIBLE_PRICE = 500


def extract_year(title: str) -> int:
    match = re.search(r"\b(199\d|20[0-2]\d)\b", title)
    return int(match.group(1)) if match else 2010


def scrape(options: ScrapeOptions) -> List[Dict[str, Any]]:
    make = options.make or ""
    model = options.model or ""
    max_price = options.max_price

    print(f"--- Craigslist: {make.capitalize()} {model.capitalize()} ---")
    results: List[Dict[str, Any]] = []
    query_parts = [part for part in [make, model] if part]
    search_query = "+".join(query_parts).replace(" ", "+").lower()
    search_url = f"https://sfbay.craigslist.org/search/cta?query={search_query}"

    res = requests.get(search_url, headers=headers)
    if res.status_code in (403, 429):
        print(f"Craigslist returned {res.status_code} (rate-limited/blocked) — backing off, skipping this run.")
        return results
    if res.status_code != 200:
        print(f"Craigslist returned unexpected status {res.status_code}, skipping.")
        return results

    soup = BeautifulSoup(res.text, "html.parser")
    listings = soup.find_all("li", class_="cl-static-search-result")[:5]

    for item in listings:
        try:
            title_elem = item.find("div", class_="title")
            price_elem = item.find("div", class_="price")
            link_elem = item.find("a")

            if not title_elem or not link_elem:
                continue

            title = title_elem.text.strip()
            title_lower = title.lower()

            # Craigslist's `query=` param does loose keyword matching, not
            # an exact make+model filter -- a search for "toyota nx" (a
            # combination that doesn't exist; NX is a Lexus model) can
            # still return unrelated ads (a Camry, a Tacoma, even a real
            # Lexus NX). The old code trusted the query terms to label
            # every result, which silently mislabeled real listings with
            # a fabricated make/model. Requiring both terms to actually
            # appear in the ad's own title rejects nonsense combinations
            # outright and filters loose/irrelevant matches on real ones.
            if make and make.lower() not in title_lower:
                continue
            if model and model.lower() not in title_lower:
                continue

            item_url = link_elem["href"]

            price = 0
            if price_elem:
                price_str = price_elem.text.replace("$", "").replace(",", "").strip()
                if price_str.isdigit():
                    price = int(price_str)

            if price < MIN_PLAUSIBLE_PRICE:
                continue

            if max_price and price > max_price:
                continue

            img_elem = item.find("img")
            photo_url = (
                img_elem["src"] if img_elem and img_elem.has_attr("src") else None
            )

            location_elem = item.find("div", class_="location")
            city = location_elem.text.strip() if location_elem else None

            results.append(
                {
                    "marketplace_source": "craigslist",
                    "original_url": item_url,
                    "make": make.capitalize(),
                    "model": model.capitalize(),
                    "model_year": extract_year(title),
                    "price": price,
                    "city": city,
                    "photos": [photo_url] if photo_url else [],  # Add this
                }
            )

        except Exception:
            pass

    # Jittered delay so repeated calls (once per saved search) don't hit
    # Craigslist at a perfectly uniform cadence.
    time.sleep(random.uniform(2, 4))
    return results
