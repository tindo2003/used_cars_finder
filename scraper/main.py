import os
from supabase import create_client, Client
from providers import craigslist, ebay, dealeron
import time
import random

# 1. Setup
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SECRET_KEY")

if not url or not key:
    raise ValueError("Missing Supabase credentials!")

supabase: Client = create_client(url, key)


DEALERS = [
    {"url": "https://www.stevenscreektoyota.com", "platform": "dealeron"},
    {"url": "https://www.capitolhonda.com", "platform": "dealeron"},
]


def run_scraper():
    print("Fetching saved searches from Supabase...")
    response = (
        supabase.table("saved_searches").select("*").eq("is_active", True).execute()
    )
    searches = response.data

    # --- 1. Scrape Marketplaces (Craigslist/eBay) based on Saved Searches ---
    active_marketplaces = [craigslist.scrape, ebay.scrape]

    for search in searches:
        make = search.get("make") or ""
        model = search.get("model") or ""
        max_price = search.get("max_price")

        if not make and not model:
            continue

        print(f"\nEvaluating target: {make.capitalize()} {model.capitalize()}")

        for provider_func in active_marketplaces:
            cars_found = provider_func(make, model, max_price)
            save_cars_to_db(cars_found)

        # --- 2. Scrape Dealerships (Independently of user searches) ---
        # Dealerships have their own inventory; we scrape their full used list
        for dealer in DEALERS:
            if dealer["platform"] == "dealeron":
                # Sleep before hitting a new dealership website
                wait_time = random.uniform(5, 10)
                print(f"Waiting {wait_time:.2f} seconds before next dealer...")
                time.sleep(wait_time)

                cars_found = dealeron.scrape(dealer["url"], None, None, None)
                save_cars_to_db(cars_found)


def save_cars_to_db(cars):
    """Helper to keep code clean and dry"""
    for car in cars:
        car["status"] = "active"
        try:
            supabase.table("listings").upsert(car, on_conflict="original_url").execute()
            print(
                f"✅ Saved [{car['marketplace_source']}]: {car.get('model_year')} {car.get('make')} - ${car.get('price')}"
            )
        except Exception as e:
            print(f"Error saving to DB: {e}")


if __name__ == "__main__":
    run_scraper()
    print("\nAutomated scraping complete.")
