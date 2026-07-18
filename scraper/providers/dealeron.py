from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import base64
import random


def extract_price(v):
    """
    data-dotagging-item-price is a third-party analytics tag and is
    unreliable (observed wildly wrong values). The real price lives in
    data-pricelib, a base64-encoded "key:value;key:value" string, e.g.
    "Selling Price:25888.0;...;calc_INTERNET PRICE:25973.0;...". Prefer
    that field's Internet Price, which matches the site's displayed price.
    """
    pricelib = v.get("data-pricelib")
    if pricelib:
        try:
            decoded = base64.b64decode(pricelib).decode("utf-8")
            fields = dict(
                part.partition(":")[::2] for part in decoded.split(";") if ":" in part
            )
            internet_price = fields.get("calc_INTERNET PRICE") or fields.get(
                "Selling Price"
            )
            if internet_price:
                return float(internet_price)
        except Exception:
            pass

    # Fall back to the analytics tag if pricelib is missing/unparseable
    return float(v.get("data-dotagging-item-price", "0"))


def extract_vehicle_data(v, base_url):
    """
    Extracts vehicle details from a BeautifulSoup element.
    v: The BeautifulSoup element representing the vehicle card div.
    """
    try:
        # Extract from data attributes
        make = v.get("data-make", "Unknown")
        model = v.get("data-model", "Unknown")
        year = int(v.get("data-year", 0))

        price = extract_price(v)

        # Extract Link (The specific structure from your HTML)
        link_elem = v.find("a", class_="hero-carousel__item--viewvehicle")
        link = link_elem.get("href", "#") if link_elem else "#"

        # Extract Image
        img_elem = v.find("img", class_="hero-carousel__background-image--grid")
        img_src = img_elem.get("src") if img_elem else None

        # If the src starts with /, prepend the base_url
        if img_src and img_src.startswith("/"):
            photo_url = f"{base_url.rstrip('/')}{img_src}"
        else:
            photo_url = img_src

        # VIN (useful for preventing duplicates in the database)
        vin = v.get("data-vin") or None

        return {
            "marketplace_source": "dealeron",
            "original_url": link,
            "vin": vin,
            "make": make,
            "model": model,
            "model_year": year,
            "price": price,
            "photos": [photo_url] if photo_url else [],
        }
    except Exception as e:
        print(f"Skipping vehicle due to parsing error: {e}")
        return None


def scrape(base_url, make=None, model=None, max_price=None, max_pages=300):
    print(f"--- DealerOn (Browser): {base_url} ---")
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 1. Navigate to the page
        page.goto(f"{base_url.rstrip('/')}/searchused.aspx", wait_until="networkidle")

        # 2. PROBE: Find the container
        possible_containers = [
            ".srp-inventory",
            ".inventory_list",
            ".inventory-results",
        ]
        inventory_selector = None

        for selector in possible_containers:
            if page.query_selector(selector):
                inventory_selector = selector
                page.wait_for_selector(inventory_selector)
                print(f"Detected inventory container: {inventory_selector}")
                break

        if not inventory_selector:
            print(f"Inventory container not found at {base_url}. Aborting.")
            browser.close()
            return results

        # 2. Set 'Show: 96' dropdown
        try:
            page.click(".pagination-dropdown")
            page.wait_for_timeout(500)
            page.click("button[data-value='96']")
            page.wait_for_timeout(3000)  # Wait for page to refresh
        except:
            print("Pagination dropdown not found, using default...")

        # 3. PAGINATION LOOP
        page_count = 0
        while page_count < max_pages:
            page_count += 1
            print(f"--- Scraping Page {page_count} ---")

            # Clear out potential overlays (cookie banners/chat widgets) that intercept clicks
            page.evaluate("""
                const overlays = document.querySelectorAll('#ca-consent-root, #podium-website-widget, .headerWrapper');
                overlays.forEach(el => el.style.display = 'none');
            """)

            # Parse the current page
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            vehicles = soup.find_all("div", class_="vehicle-card")
            for v in vehicles:
                car_data = extract_vehicle_data(v, base_url)
                if car_data:
                    # Apply filters
                    if make and make.lower() not in car_data["make"].lower():
                        continue
                    if model and model.lower() not in car_data["model"].lower():
                        continue
                    if max_price and car_data["price"] > max_price:
                        continue

                    results.append(car_data)

            # Check for 'Next' button and handle it
            next_button = page.query_selector(
                ".pagination__item--next:not(.disabled) > a"
            )
            if next_button and page_count < max_pages:
                print("Clicking 'Next' page...")
                try:
                    # Scroll into view and force the click
                    next_button.scroll_into_view_if_needed()
                    next_button.click(force=True)
                    # Wait for the network to idle after the click to ensure the new page loads
                    page.wait_for_load_state("networkidle")
                    # Extra buffer for JS hydration
                    page.wait_for_timeout(2000)
                except Exception as e:
                    print(f"Could not click 'Next': {e}")
                    break
            else:
                print("No more pages found.")
                break

        # 4. Capture the fully expanded HTML page content after all scrolls finish
        html = page.content()
        browser.close()

    return results
