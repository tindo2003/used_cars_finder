import re
import requests
from bs4 import BeautifulSoup
import time

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def extract_year(title):
    match = re.search(r"\b(199\d|20[0-2]\d)\b", title)
    return int(match.group(1)) if match else 2010


def scrape(make, model, max_price):
    print(f"--- Craigslist: {make.capitalize()} {model.capitalize()} ---")
    results = []
    query_parts = [part for part in [make, model] if part]
    search_query = "+".join(query_parts).replace(" ", "+").lower()
    search_url = f"https://sfbay.craigslist.org/search/cta?query={search_query}"

    res = requests.get(search_url, headers=headers)
    if res.status_code != 200:
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
            item_url = link_elem["href"]

            price = 0
            if price_elem:
                price_str = price_elem.text.replace("$", "").replace(",", "").strip()
                if price_str.isdigit():
                    price = int(price_str)

            if max_price and price > max_price:
                continue

            img_elem = item.find("img")
            photo_url = (
                img_elem["src"] if img_elem and img_elem.has_attr("src") else None
            )

            results.append(
                {
                    "marketplace_source": "craigslist",
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
