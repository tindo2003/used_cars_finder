from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup, Tag
import base64
import random
from typing import Any, Dict, List, Optional

from options import ScrapeOptions
from utils.pagination import page_did_not_advance


def _attr(tag: Tag, name: str) -> Optional[str]:
    """
    HTML attributes are technically str | list[str] | None in bs4's own
    typing (an attribute like class can be multi-valued) -- every
    attribute this scraper reads is single-valued in practice, so this
    normalizes to a plain Optional[str].
    """
    value = tag.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _find_tag(parent: Tag, name: str, class_: str) -> Optional[Tag]:
    """.find() can return a NavigableString instead of a Tag; every use
    here wants a Tag specifically (to read attributes off of)."""
    found = parent.find(name, class_=class_)
    return found if isinstance(found, Tag) else None


def extract_price(v: Tag) -> float:
    """
    data-dotagging-item-price is a third-party analytics tag and is
    unreliable (observed wildly wrong values). The real price lives in
    data-pricelib, a base64-encoded "key:value;key:value" string, e.g.
    "Selling Price:25888.0;...;calc_INTERNET PRICE:25973.0;...". Prefer
    that field's Internet Price, which matches the site's displayed price.
    """
    pricelib = _attr(v, "data-pricelib")
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
    return float(_attr(v, "data-dotagging-item-price") or "0")


def extract_mileage(v: Tag) -> Optional[int]:
    odometer = _attr(v, "data-odometer")
    if odometer and odometer.isdigit():
        return int(odometer)
    return None


def extract_posted_at(v: Tag) -> Optional[str]:
    # data-dotagging-item-inventory-date is "YYYY/MM/DD"; Postgres accepts
    # "YYYY-MM-DD" as a valid timestamp/date literal directly.
    inventory_date = _attr(v, "data-dotagging-item-inventory-date")
    if inventory_date:
        return inventory_date.replace("/", "-")
    return None


def extract_vehicle_data(
    v: Tag, base_url: str, city: Optional[str] = None, dealer_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Extracts vehicle details from a BeautifulSoup element.
    v: The BeautifulSoup element representing the vehicle card div.
    """
    try:
        # Extract from data attributes
        make = _attr(v, "data-make") or "Unknown"
        model = _attr(v, "data-model") or "Unknown"
        year = int(_attr(v, "data-year") or 0)

        price = extract_price(v)

        # Extract Link (The specific structure from your HTML)
        link_elem = _find_tag(v, "a", "hero-carousel__item--viewvehicle")
        link = (_attr(link_elem, "href") if link_elem else None) or "#"

        # Extract Image
        img_elem = _find_tag(v, "img", "hero-carousel__background-image--grid")
        img_src = _attr(img_elem, "src") if img_elem else None

        # If the src starts with /, prepend the base_url
        photo_url: Optional[str]
        if img_src and img_src.startswith("/"):
            photo_url = f"{base_url.rstrip('/')}{img_src}"
        else:
            photo_url = img_src

        # VIN (useful for preventing duplicates in the database)
        vin = _attr(v, "data-vin") or None

        return {
            "marketplace_source": "dealeron",
            "original_url": link,
            "vin": vin,
            "make": make,
            "model": model,
            "trim": _attr(v, "data-trim") or None,
            "model_year": year,
            "price": price,
            "mileage": extract_mileage(v),
            "seller_type": "dealer",
            "transmission": _attr(v, "data-trans") or None,
            "fuel_type": _attr(v, "data-fueltype") or None,
            "city": city,
            "dealer_name": dealer_name,
            "posted_at": extract_posted_at(v),
            "photos": [photo_url] if photo_url else [],
        }
    except Exception as e:
        print(f"Skipping vehicle due to parsing error: {e}")
        return None


def _scroll_until_stable(page: Any, max_attempts: int = 20) -> None:
    """
    Some DealerOn sites (confirmed live: Lexus Stevens Creek) render
    the vehicle-card grid virtualized -- cards for the CURRENT page
    mount progressively as you scroll, from data the site already
    fetched in one API call, not via additional page/network requests.
    A single DOM snapshot right after `networkidle` only captures
    whatever happened to render first (as few as 4 of a real 56 on that
    dealer, confirmed by live inspection), even though upping the
    display-count (see the "Show 96" click above) makes the site
    correctly report "no more pages" once everything nominally fits on
    one page -- so the old code silently under-scraped without ever
    detecting anything was wrong. Scrolling to the bottom repeatedly
    (bounded by max_attempts) until the rendered count stops growing
    fixes this for virtualized sites, and costs one cheap no-op
    scroll+wait on sites that already render everything up front.
    """
    previous_count = page.evaluate("document.querySelectorAll('.vehicle-card').length")
    for _ in range(max_attempts):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)
        current_count = page.evaluate("document.querySelectorAll('.vehicle-card').length")
        if current_count == previous_count:
            break
        previous_count = current_count


def scrape(base_url: str, options: Optional[ScrapeOptions] = None) -> List[Dict[str, Any]]:
    options = options or ScrapeOptions()
    max_pages = options.max_pages or 300

    print(f"--- DealerOn (Browser): {base_url} ---")
    results: List[Dict[str, Any]] = []

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
        previous_page_vins = None
        while page_count < max_pages:
            page_count += 1
            print(f"--- Scraping Page {page_count} ---")

            # Clear out potential overlays (cookie banners/chat widgets) that intercept clicks
            page.evaluate("""
                const overlays = document.querySelectorAll('#ca-consent-root, #podium-website-widget, .headerWrapper');
                overlays.forEach(el => el.style.display = 'none');
            """)

            _scroll_until_stable(page)

            # Parse the current page
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")

            vehicles = soup.find_all("div", class_="vehicle-card")

            # A "Next" click can succeed (no exception) without the page
            # actually changing -- e.g. a site with only one real page of
            # results but an always-present Next button. Confirmed live:
            # 12 real vehicles scraped 20 times over before this guard
            # existed. See pagination.page_did_not_advance for exactly
            # what does (and doesn't) count as a stall.
            current_page_vins = frozenset(v.get("data-vin") for v in vehicles if v.get("data-vin"))
            if page_did_not_advance(current_page_vins, previous_page_vins):
                print("Pagination did not advance (same vehicles as the previous page) -- stopping.")
                break
            previous_page_vins = current_page_vins

            for v in vehicles:
                car_data = extract_vehicle_data(v, base_url, city=options.city, dealer_name=options.dealer_name)
                if car_data:
                    # Apply filters
                    if options.make and options.make.lower() not in car_data["make"].lower():
                        continue
                    if options.model and options.model.lower() not in car_data["model"].lower():
                        continue
                    if options.max_price and car_data["price"] > options.max_price:
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
                    # DealerOn's robots.txt sets "Crawl-delay: 10" (confirmed
                    # on stevenscreektoyota.com and fremonthyundai.com) —
                    # honor it between page fetches rather than hammering.
                    page.wait_for_timeout(10000)
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
