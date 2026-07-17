import os
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

# Pull credentials from GitHub Actions environment
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SECRET_KEY")

if not url or not key:
    raise ValueError("Missing Supabase credentials!")

supabase: Client = create_client(url, key)

search_url = "https://sfbay.craigslist.org/search/cta?query=honda+civic"

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def run_scraper():
    print(f"Scraping: {search_url}")
    response = requests.get(search_url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to load page. Status Code: {response.status_code}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    # 🚨 FIX: Target the static HTML fallback that Craigslist sends to bots
    listings = soup.find_all("li", class_="cl-static-search-result")

    print(f"Found {len(listings)} raw listings in the HTML. Parsing now...")

    for item in listings[:10]:  # Limit to 10 for testing
        try:
            # In the static version, the title is inside a simple <div>
            title_elem = item.find("div", class_="title")
            price_elem = item.find("div", class_="price")
            link_elem = item.find("a")

            if not title_elem or not link_elem:
                continue

            title = title_elem.text.strip()
            original_url = link_elem["href"]

            # Clean the price string (e.g., "$14,500" -> 14500)
            price = 0
            if price_elem:
                price_str = price_elem.text.replace("$", "").replace(",", "").strip()
                if price_str.isdigit():
                    price = int(price_str)

            new_car = {
                "marketplace_source": "craigslist",
                "original_url": original_url,
                "make": "Honda",
                "model": "Civic",
                "model_year": 2015,  # Hardcoded temporarily
                "price": price,
                "status": "active",
            }

            print(f"✅ Parsed: {title} - ${price}")
            supabase.table("listings").upsert(
                new_car, on_conflict="original_url"
            ).execute()

        except Exception as e:
            print(f"Error parsing item: {e}")


if __name__ == "__main__":
    run_scraper()
    print("Scraping complete. Check Next.js!")
