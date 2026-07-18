import argparse
import os
from supabase import create_client, Client
from providers import craigslist, ebay, dealeron, dealerinspire
from options import ScrapeOptions
import time
import random

DEALERS = [
    {"url": "https://www.stevenscreektoyota.com", "platform": "dealeron"},
    {"url": "https://www.capitolhonda.com", "platform": "dealerinspire"},
]

DEALER_SCRAPERS = {
    "dealeron": dealeron.scrape,
    "dealerinspire": dealerinspire.scrape,
}


def get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        raise ValueError("Missing Supabase credentials!")
    return create_client(url, key)


def run_scraper(dry_run=False, max_pages=None):
    supabase = None
    if not dry_run:
        supabase = get_supabase()
        print("Connected to Supabase.")
    else:
        print("--- RUNNING IN DRY RUN MODE (No DB connection) ---")

    print(f"Fetching saved searches... {'(DRY RUN MODE)' if dry_run else ''}")

    # Only fetch from DB if NOT a dry run
    if not dry_run:
        response = (
            supabase.table("saved_searches").select("*").eq("is_active", True).execute()
        )
        searches = response.data
    else:
        # Dummy data for dry run testing
        searches = [{"make": "Toyota", "model": "Camry", "max_price": 20000}]

    # --- 1. Scrape Marketplaces (Craigslist/eBay) based on Saved Searches ---
    active_marketplaces = [craigslist.scrape, ebay.scrape]

    for search in searches:
        make = search.get("make") or ""
        model = search.get("model") or ""

        if not make and not model:
            continue

        print(f"\nEvaluating target: {make.capitalize()} {model.capitalize()}")

        options = ScrapeOptions(make=make, model=model, max_price=search.get("max_price"))
        for provider_func in active_marketplaces:
            cars_found = provider_func(options)
            save_cars_to_db(cars_found, dry_run, supabase)

    # --- 2. Scrape Dealerships (Independently of user searches) ---
    # Dealerships have their own inventory; we scrape their full used list
    for dealer in DEALERS:
        scraper_func = DEALER_SCRAPERS.get(dealer["platform"])
        if not scraper_func:
            print(f"Unknown platform '{dealer['platform']}' for {dealer['url']}, skipping.")
            continue

        # Sleep before hitting a new dealership website
        wait_time = random.uniform(5, 10)
        print(f"Waiting {wait_time:.2f} seconds before next dealer...")
        time.sleep(wait_time)

        cars_found = scraper_func(dealer["url"], ScrapeOptions(max_pages=max_pages))
        save_cars_to_db(cars_found, dry_run, supabase)


def save_cars_to_db(cars, dry_run, supabase):  # Added supabase as an argument
    for car in cars:
        if dry_run:
            print(
                f"🔍 [DRY RUN] Would save: {car.get('make')} {car.get('model')} - ${car.get('price')}"
            )
        else:
            car["status"] = "active"
            supabase.table("listings").upsert(car, on_conflict="original_url").execute()
            print(
                f"✅ Saved: {car.get('model_year')} {car.get('make')} - ${car.get('price')}"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the car scraper.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print results without saving to Supabase",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Limit how many inventory pages each dealer scraper fetches (useful for quick tests)",
    )
    args = parser.parse_args()

    run_scraper(dry_run=args.dry_run, max_pages=args.max_pages)
