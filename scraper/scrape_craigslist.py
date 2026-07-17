import os
import time
import re
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

# 1. Supabase Setup
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SECRET_KEY")

if not url or not key:
    raise ValueError("Missing Supabase credentials!")

supabase: Client = create_client(url, key)

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def run_scraper():
    print("Fetching saved searches from Supabase...")

    # 2. Get all active searches from the database
    response = (
        supabase.table("saved_searches").select("*").eq("is_active", True).execute()
    )
    searches = response.data

    if not searches:
        print("No active searches found. Exiting.")
        return

    print(f"Found {len(searches)} active search parameters.\n")

    # 3. Loop through each saved search
    for search in searches:
        make = search.get("make") or ""
        model = search.get("model") or ""
        max_price = search.get("max_price")

        # Skip if both are empty
        if not make and not model:
            continue

        # Build the query string (e.g., "Toyota+Tacoma")
        query_parts = [part for part in [make, model] if part]
        search_query = "+".join(query_parts).replace(" ", "+").lower()
        search_url = f"https://sfbay.craigslist.org/search/cta?query={search_query}"

        print(f"--- Scraping for: {make.capitalize()} {model.capitalize()} ---")

        res = requests.get(search_url, headers=headers)
        if res.status_code != 200:
            print(f"Failed to load page. Status: {res.status_code}")
            continue

        soup = BeautifulSoup(res.text, "html.parser")
        listings = soup.find_all("li", class_="cl-static-search-result")

        print(f"Found {len(listings)} raw listings.")

        # 4. Parse the listings
        for item in listings[:10]:  # Limiting to 10 per query for MVP to prevent blocks
            try:
                title_elem = item.find("div", class_="title")
                price_elem = item.find("div", class_="price")
                link_elem = item.find("a")

                if not title_elem or not link_elem:
                    continue

                title = title_elem.text.strip()
                original_url = link_elem["href"]

                # Price cleaning
                price = 0
                if price_elem:
                    price_str = (
                        price_elem.text.replace("$", "").replace(",", "").strip()
                    )
                    if price_str.isdigit():
                        price = int(price_str)

                # Skip if it's over the user's max price
                if max_price and price > max_price:
                    continue

                # Extract the year from the title (e.g., looking for "2018" or "1999")
                year_match = re.search(r"\b(199\d|20[0-2]\d)\b", title)
                model_year = int(year_match.group(1)) if year_match else 2010

                new_car = {
                    "marketplace_source": "craigslist",
                    "original_url": original_url,
                    "make": make.capitalize() if make else "Unknown",
                    "model": model.capitalize() if model else "Unknown",
                    "model_year": model_year,
                    "price": price,
                    "status": "active",
                }

                supabase.table("listings").upsert(
                    new_car, on_conflict="original_url"
                ).execute()
                print(f"✅ Saved: {title} - ${price}")

            except Exception as e:
                print(f"Error parsing item: {e}")

        # Be nice to Craigslist's servers and pause before the next search
        time.sleep(3)


if __name__ == "__main__":
    run_scraper()
    print("\nAutomated scraping complete.")
