import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import sync_playwright

from options import ScrapeOptions
from utils.pagination import page_did_not_advance


def _attr(tag: Tag, name: str) -> Optional[str]:
    value = tag.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _find_tag(parent: Tag, name: str, class_: str) -> Optional[Tag]:
    found = parent.find(name, class_=class_)
    return found if isinstance(found, Tag) else None


def _url_path(url: str) -> str:
    """Path only, no domain/query -- the stable join key between the
    CollectionPage JSON-LD's absolute, query-free `url` and a card's
    relative href (which carries a `?priorityType=spv` tracking param)."""
    return urlsplit(url).path


def _card_original_url(card: Tag, base_url: str) -> Optional[str]:
    title_el = _find_tag(card, "h2", "vehicle-card-title")
    title_link = title_el.find("a") if title_el else None
    href = _attr(title_link, "href") if isinstance(title_link, Tag) else None
    if not href:
        return None
    return f"{base_url.rstrip('/')}{href}" if href.startswith("/") else href


def _card_vin(card: Tag, base_url: str, json_ld_offers: Dict[str, Dict[str, Any]]) -> Optional[str]:
    url = _card_original_url(card, base_url)
    if not url:
        return None
    offer = json_ld_offers.get(_url_path(url))
    vin = offer.get("vehicleIdentificationNumber") if offer else None
    return vin if isinstance(vin, str) else None


def parse_json_ld_offers(html: str) -> Dict[str, Dict[str, Any]]:
    """
    Every Dealer.com used-inventory page embeds a schema.org `CollectionPage`
    <script type="application/ld+json"> block whose `about.offers.itemOffered`
    is a full structured list of every vehicle on the page (VIN, brand, model,
    year, price, transmission, fuelType, ...) -- confirmed live against
    Premier Subaru of Fremont, far more reliable than scraping visible card
    text/badges (no third-party VIN badge dependency, no title-string
    make/model guessing). Keyed by URL path so callers can join a DOM card
    to its structured data without relying on rendering order.

    One caveat found live: this blob's `mileageFromOdometer.value` is
    truncated to thousands (e.g. a real 32,373-mile car reports "32") --
    unreliable, so mileage is deliberately NOT read from here; callers
    should keep reading mileage off the card's own rendered text.
    """
    offers: Dict[str, Dict[str, Any]] = {}
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        items = data.get("about", {}).get("offers", {}).get("itemOffered")
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and item.get("url"):
                offers[_url_path(item["url"])] = item
    return offers


def extract_vehicle_data(
    card: Tag,
    base_url: str,
    json_ld_offers: Optional[Dict[str, Dict[str, Any]]] = None,
    city: Optional[str] = None,
    dealer_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Extracts vehicle details for a Dealer.com used-inventory SRP card
    (li.vehicle-card.vehicle-card-detailed). Confirmed live against
    Premier Subaru of Fremont -- see research/bay-area-dealer-candidates.md.

    Prefers the matching entry in `json_ld_offers` (see parse_json_ld_offers)
    for vin/make/model/model_year/price/transmission/fuel_type -- the card's
    own HTML lacks a reliable VIN entirely (only a slow-loading third-party
    privacy widget, not always present) and its title is unstructured free
    text. Falls back to parsing the card directly if no JSON-LD match is
    found (e.g. a future template change), so a single missing entry can't
    take out a whole page of otherwise-good data. Mileage always comes from
    the card itself -- see parse_json_ld_offers' docstring for why the
    JSON-LD figure can't be trusted for that one field.
    """
    try:
        original_url = _card_original_url(card, base_url) or "#"
        offer = (json_ld_offers or {}).get(_url_path(original_url)) if original_url != "#" else None

        if offer:
            vin = offer.get("vehicleIdentificationNumber")
            make = offer.get("brand", {}).get("name")
            model = offer.get("model")
            model_year = offer.get("vehicleModelDate") or 0
            transmission = offer.get("vehicleTransmission")
            fuel_type = offer.get("fuelType")
            price_str = offer.get("offers", {}).get("price")
            price = float(price_str) if price_str else 0.0
            photo_url = offer.get("image")
        else:
            # Fallback: same free-text title parsing every other provider
            # in this codebase uses when no structured source is available.
            title_el = _find_tag(card, "h2", "vehicle-card-title")
            title_link = title_el.find("a") if title_el else None
            title_text = title_link.get_text(strip=True) if isinstance(title_link, Tag) else ""
            tokens = title_text.strip().split()
            year_match = re.match(r"^\d{4}$", tokens[0]) if tokens else None
            model_year = int(tokens[0]) if year_match else 0
            rest = tokens[1:] if year_match else tokens
            vin = None
            make = rest[0] if rest else None
            model = " ".join(rest[1:]) if len(rest) > 1 else None
            transmission = None
            fuel_type = None
            price = 0.0
            price_el = _find_tag(card, "dd", "final-price")
            if price_el:
                price_value = _find_tag(price_el, "span", "price-value")
                text = price_value.get_text(strip=True) if price_value else price_el.get_text(strip=True)
                match = re.search(r"\$([\d,]+)", text)
                if match:
                    price = float(match.group(1).replace(",", ""))
            img_el = card.find("img")
            photo_url = _attr(img_el, "src") if isinstance(img_el, Tag) else None
            if photo_url and photo_url.startswith("/"):
                photo_url = f"{base_url.rstrip('/')}{photo_url}"

        mileage = None
        highlight = _find_tag(card, "div", "vehicle-card-highlight")
        if highlight:
            for badge in highlight.find_all(class_="highlight-badge"):
                if not isinstance(badge, Tag):
                    continue
                mileage_match = re.match(r"([\d,]+)\s*miles", badge.get_text(strip=True), re.IGNORECASE)
                if mileage_match:
                    mileage = int(mileage_match.group(1).replace(",", ""))
                    break

        return {
            "marketplace_source": "dealerdotcom",
            "original_url": original_url,
            "vin": vin,
            "make": make or "Unknown",
            "model": model or "Unknown",
            "trim": None,
            "model_year": model_year,
            "price": price,
            "mileage": mileage,
            "seller_type": "dealer",
            "transmission": transmission,
            "fuel_type": fuel_type,
            "city": city,
            "dealer_name": dealer_name,
            "posted_at": None,
            "photos": [photo_url] if photo_url else [],
        }
    except Exception as e:
        print(f"Skipping vehicle due to parsing error: {e}")
        return None


def scrape(base_url: str, options: Optional[ScrapeOptions] = None) -> List[Dict[str, Any]]:
    options = options or ScrapeOptions()
    max_pages = options.max_pages or 300

    print(f"--- Dealer.com (Browser): {base_url} ---")
    results: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        # Akamai Bot Manager fronts these sites and is more aggressive than
        # the Cloudflare gate dealerinspire.py handles -- confirmed live
        # that a plain HTTP request (even for /robots.txt) gets flagged
        # "BOT-BROWSER-IMPERSONATOR" and 403'd, while a real rendering
        # engine gets through. Same stealth approach as dealerinspire.py.
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

        start = 0
        page_num = 1
        previous_page_vins: Optional[frozenset[str]] = None

        while page_num <= max_pages:
            print(f"--- Scraping Page {page_num} (start={start}) ---")
            page.goto(
                f"{base_url.rstrip('/')}/used-inventory/index.htm?start={start}",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            try:
                page.wait_for_selector(".vehicle-card", timeout=15000)
            except Exception:
                print(f"Inventory container not found at {base_url}. Aborting.")
                break

            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            json_ld_offers = parse_json_ld_offers(html)
            cards = [
                c
                for c in soup.find_all("li", class_="vehicle-card")
                if isinstance(c, Tag) and "vehicle-card-detailed" in (c.get("class") or [])
            ]
            if not cards:
                break

            page_vins = [_card_vin(c, base_url, json_ld_offers) for c in cards]
            current_page_vins = frozenset(vin for vin in page_vins if vin)
            if page_did_not_advance(current_page_vins, previous_page_vins):
                print("Pagination did not advance (same vehicles as the previous page) -- stopping.")
                break
            previous_page_vins = current_page_vins

            for card in cards:
                car_data = extract_vehicle_data(
                    card, base_url, json_ld_offers, city=options.city, dealer_name=options.dealer_name
                )
                if car_data:
                    if options.make and options.make.lower() not in car_data["make"].lower():
                        continue
                    if options.model and options.model.lower() not in car_data["model"].lower():
                        continue
                    if options.max_price and car_data["price"] > options.max_price:
                        continue
                    results.append(car_data)

            # No Crawl-delay documented in robots.txt for this platform
            # (confirmed live) -- a modest delay between page fetches to
            # stay polite regardless, same reasoning as dealersocket_gemini.py.
            page.wait_for_timeout(3000)
            start += len(cards)
            page_num += 1

        browser.close()

    return results
