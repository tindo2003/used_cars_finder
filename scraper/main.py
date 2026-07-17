import os
from supabase import create_client, Client
from providers import craigslist, ebay

# 1. Setup
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SECRET_KEY")

if not url or not key:
    raise ValueError("Missing Supabase credentials!")

supabase: Client = create_client(url, key)


def run_scraper():
    print("Fetching saved searches from Supabase...")
    response = (
        supabase.table("saved_searches").select("*").eq("is_active", True).execute()
    )
    searches = response.data

    if not searches:
        print("No active searches found. Exiting.")
        return

    # 2. Register your active provider modules here
    active_providers = [craigslist.scrape, ebay.scrape]

    # 3. Execute
    for search in searches:
        make = search.get("make") or ""
        model = search.get("model") or ""
        max_price = search.get("max_price")

        if not make and not model:
            continue

        print(f"\nEvaluating target: {make.capitalize()} {model.capitalize()}")

        for provider_func in active_providers:
            # The orchestrator doesn't care HOW the provider gets the data,
            # as long as it returns the standardized list of dictionaries.
            cars_found = provider_func(make, model, max_price)

            for car in cars_found:
                car["status"] = "active"
                supabase.table("listings").upsert(
                    car, on_conflict="original_url"
                ).execute()
                print(
                    f"✅ Saved [{car['marketplace_source']}]: {car.get('model_year')} {car.get('make')} - ${car.get('price')}"
                )


if __name__ == "__main__":
    run_scraper()
    print("\nAutomated scraping complete.")
