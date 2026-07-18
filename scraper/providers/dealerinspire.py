from playwright.sync_api import sync_playwright
import json

from options import ScrapeOptions


def extract_vehicle_data(card, base_url, city=None, dealer_name=None):
    """
    Extracts vehicle details from a Playwright element handle for a
    DealerInspire ".result-wrap" card. Unlike DealerOn, all vehicle fields
    are packed into a single "data-vehicle" JSON attribute.

    Note: mileage and transmission are not exposed on this card in any form
    (not in data-vehicle, not in the rendered HTML) — DealerInspire only
    shows those on each vehicle's own detail page, which we don't visit
    here to avoid multiplying scrape time per vehicle.
    """
    try:
        data = json.loads(card.get_attribute("data-vehicle") or "{}")

        link_elem = card.query_selector("a.hit-link")
        link = link_elem.get_attribute("href") if link_elem else "#"

        img_elem = card.query_selector("img")
        img_src = img_elem.get_attribute("src") if img_elem else None
        if img_src and img_src.startswith("/"):
            photo_url = f"{base_url.rstrip('/')}{img_src}"
        else:
            photo_url = img_src

        return {
            "marketplace_source": "dealerinspire",
            "original_url": link,
            "vin": data.get("vin") or None,
            "make": data.get("make", "Unknown"),
            "model": data.get("model", "Unknown"),
            "trim": data.get("trim") or None,
            "model_year": int(data.get("year") or 0),
            "price": float(data.get("price") or 0),
            "seller_type": "dealer",
            "fuel_type": data.get("fueltype") or None,
            "city": city,
            "dealer_name": dealer_name,
            "posted_at": data.get("date_in_stock") or None,
            "photos": [photo_url] if photo_url else [],
        }
    except Exception as e:
        print(f"Skipping vehicle due to parsing error: {e}")
        return None


def scrape(base_url, options: ScrapeOptions = None):
    options = options or ScrapeOptions()
    max_pages = options.max_pages or 50

    print(f"--- DealerInspire (Browser): {base_url} ---")
    results = []

    with sync_playwright() as p:
        # DealerInspire sites sit behind Cloudflare bot-protection, which
        # blocks vanilla headless Chromium. A realistic UA + hiding the
        # automation fingerprints below is enough to pass the check.
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_page(
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
        )
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # domcontentloaded rather than networkidle: some DealerInspire sites
        # run chat widgets/trackers that poll continuously and never let the
        # network go idle, which was timing out page.goto entirely. The
        # wait_for_selector below already confirms the real content loaded.
        page.goto(f"{base_url.rstrip('/')}/used-vehicles/", wait_until="domcontentloaded")

        # Dismiss the cookie/privacy banner so it doesn't block scrolling/clicks
        try:
            page.click("text=Deny targeting cookies", timeout=3000)
        except Exception:
            pass

        try:
            page.wait_for_selector(".result-wrap", timeout=15000)
        except Exception:
            print(f"Inventory container not found at {base_url}. Aborting.")
            browser.close()
            return results

        # Results use numbered pagination (a "Page X of Y" widget), not
        # infinite scroll. Each "Next" click replaces the current page's
        # cards, so we parse after every click rather than accumulating DOM.
        for page_count in range(1, max_pages + 1):
            state = page.query_selector(".pagination-state")
            print(f"--- Scraping Page {page_count} ({state.inner_text() if state else '?'}) ---")

            cards = page.query_selector_all(".result-wrap")
            for card in cards:
                car_data = extract_vehicle_data(card, base_url, city=options.city, dealer_name=options.dealer_name)
                if car_data:
                    if options.make and options.make.lower() not in car_data["make"].lower():
                        continue
                    if options.model and options.model.lower() not in car_data["model"].lower():
                        continue
                    if options.max_price and car_data["price"] > options.max_price:
                        continue
                    results.append(car_data)

            next_wrapper = page.query_selector(".pagination-arrow.pagination-next")
            next_link = page.query_selector('a.go-to-page[aria-label="next page"]')
            if not next_link or (next_wrapper and "disable" in (next_wrapper.get_attribute("class") or "")):
                print("No more pages found.")
                break

            try:
                next_link.scroll_into_view_if_needed()
                next_link.click()
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"Could not click 'Next': {e}")
                break

        browser.close()

    return results
