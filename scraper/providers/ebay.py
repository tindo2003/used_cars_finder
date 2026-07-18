import re
import requests
from bs4 import BeautifulSoup
import time

from options import ScrapeOptions

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def extract_year(title):
    match = re.search(r"\b(199\d|20[0-2]\d)\b", title)
    return int(match.group(1)) if match else 2010


def scrape(options: ScrapeOptions):
    make = options.make or ""
    model = options.model or ""
    max_price = options.max_price

    print(f"--- eBay Motors: {make.capitalize()} {model.capitalize()} ---")
    results = []
    query_parts = [part for part in [make, model] if part]
    search_query = "+".join(query_parts).replace(" ", "+").lower()
    search_url = f"https://www.ebay.com/sch/i.html?_nkw={search_query}+cars&_sacat=6001"

    res = requests.get(search_url, headers=headers)
    if res.status_code != 200:
        return results

    soup = BeautifulSoup(res.text, "html.parser")
    listings = soup.find_all("div", class_="s-item__wrapper")[:6]

    for item in listings:
        try:
            title_elem = item.find("div", class_="s-item__title")
            price_elem = item.find("span", class_="s-item__price")
            link_elem = item.find("a", class_="s-item__link")

            if not title_elem or not link_elem:
                continue
            title = title_elem.text.strip()

            if "Shop on eBay" in title:
                continue

            item_url = link_elem["href"].split("?")[0]

            price = 0
            if price_elem:
                price_str = (
                    price_elem.text.split(" to ")[0]
                    .replace("$", "")
                    .replace(",", "")
                    .replace(".00", "")
                    .strip()
                )
                if price_str.isdigit():
                    price = int(price_str)

            if max_price and price > max_price:
                continue

            img_elem = item.find("img", class_="s-item__image-img")
            photo_url = img_elem.get("src") if img_elem else None

            results.append(
                {
                    "marketplace_source": "ebay",
                    "original_url": item_url,
                    "make": make.capitalize(),
                    "model": model.capitalize(),
                    "model_year": extract_year(title),
                    "price": price,
                    "photos": [photo_url] if photo_url else [],  # Add this
                }
            )
        except Exception:
            pass

    time.sleep(2)
    return results
