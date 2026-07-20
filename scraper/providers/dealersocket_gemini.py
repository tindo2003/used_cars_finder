from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup, Tag
import re
from typing import Any, Dict, List, Optional

from options import ScrapeOptions
from utils.pagination import page_did_not_advance

# Makes whose own name contains a hyphen -- needed to correctly split
# data-itemid's "Make-Model-Trim-VIN" string (see parse_item_id). Model can
# also contain a hyphen (e.g. "CR-V", "HR-V"), but that's handled by taking
# everything left over once Make and Trim are accounted for.
HYPHENATED_MAKES = {"Mercedes-Benz", "Rolls-Royce"}


def _attr(tag: Tag, name: str) -> Optional[str]:
    value = tag.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _find_tag(parent: Tag, name: str, class_: str) -> Optional[Tag]:
    found = parent.find(name, class_=class_)
    return found if isinstance(found, Tag) else None


def parse_item_id(item_id: str) -> Dict[str, Optional[str]]:
    """
    This platform never exposes make/model as their own card attributes --
    the visible title is a single free-text string (e.g. "2003 Honda CR-V
    LX FWD"). data-itemid is the platform's own internal breakdown of the
    same vehicle as "Make-Model-Trim-VIN", hyphen-joined, and is the only
    place those fields are discrete. VIN is reliably the last segment and
    Trim the second-to-last; splitting Make from Model in what's left is
    ambiguous on its own (both can contain hyphens -- "Mercedes-Benz" as a
    Make, "CR-V"/"HR-V" as a Model), so this checks HYPHENATED_MAKES first
    before assuming a single leading segment is the whole Make.
    """
    segments = item_id.split("-")
    if len(segments) < 3:
        return {"make": None, "model": None, "trim": None, "vin": None}

    vin = segments[-1] or None
    trim = segments[-2] or None
    remaining = segments[:-2]

    if len(remaining) >= 2 and f"{remaining[0]}-{remaining[1]}" in HYPHENATED_MAKES:
        make: Optional[str] = f"{remaining[0]}-{remaining[1]}"
        model: Optional[str] = "-".join(remaining[2:]) or None
    else:
        make = remaining[0] if remaining else None
        model = "-".join(remaining[1:]) or None

    return {"make": make, "model": model, "trim": trim, "vin": vin}


def extract_price(card: Tag) -> float:
    price_el = _find_tag(card, "div", "vehicle-summary-price")
    if not price_el:
        return 0.0
    match = re.search(r"\$([\d,]+)", price_el.get_text(" ", strip=True))
    return float(match.group(1).replace(",", "")) if match else 0.0


def extract_details(card: Tag) -> Dict[str, str]:
    """
    Reads the card's label/value spec rows (Mileage, Drivetrain, Exterior,
    etc. -- whichever the dealer's template includes; not a fixed set).
    Notably absent on every card checked live: Transmission and fuel type,
    which only ever show on the vehicle's own detail page -- not fetched
    here, same tradeoff DealerInspire's provider already makes.
    """
    details: Dict[str, str] = {}
    for row in card.find_all("div", class_="details-item-row"):
        if not isinstance(row, Tag):
            continue
        label_el = _find_tag(row, "div", "details-item-label")
        value_el = _find_tag(row, "div", "details-item-value")
        if label_el and value_el:
            details[label_el.get_text(strip=True).lower()] = value_el.get_text(strip=True)
    return details


def extract_mileage(details: Dict[str, str]) -> Optional[int]:
    mileage_text = details.get("mileage")
    if not mileage_text:
        return None
    digits = re.sub(r"[^\d]", "", mileage_text)
    return int(digits) if digits else None


def extract_vehicle_data(
    card: Tag, base_url: str, city: Optional[str] = None, dealer_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Extracts vehicle details from a "dealersocket-gemini" SRP card
    (div.clean-design-srp-card, wrapping an a.srp-vehicle-box link).
    """
    try:
        parsed = parse_item_id(_attr(card, "data-itemid") or "")

        link_elem = _find_tag(card, "a", "srp-vehicle-box")
        link = (_attr(link_elem, "href") if link_elem else None) or "#"

        img_elem = _find_tag(card, "img", "srp-vehiclebox-image")
        img_src = _attr(img_elem, "src") if img_elem else None
        photo_url: Optional[str]
        if img_src and img_src.startswith("/"):
            photo_url = f"{base_url.rstrip('/')}{img_src}"
        else:
            photo_url = img_src

        title_el = _find_tag(card, "h2", "vehiclebox-title-main")
        title_text = title_el.get_text(strip=True) if title_el else ""
        year_match = re.match(r"(\d{4})", title_text)
        model_year = int(year_match.group(1)) if year_match else 0

        details = extract_details(card)

        return {
            "marketplace_source": "dealersocket-gemini",
            "original_url": link,
            "vin": parsed["vin"],
            "make": parsed["make"] or "Unknown",
            "model": parsed["model"] or "Unknown",
            "trim": parsed["trim"],
            "model_year": model_year,
            "price": extract_price(card),
            "mileage": extract_mileage(details),
            "seller_type": "dealer",
            "transmission": None,
            "fuel_type": None,
            "city": city,
            "dealer_name": dealer_name,
            "posted_at": None,
            "photos": [photo_url] if photo_url else [],
        }
    except Exception as e:
        print(f"Skipping vehicle due to parsing error: {e}")
        return None


def _max_page_number(soup: BeautifulSoup) -> int:
    pagination = soup.find(class_="inventory-pagination")
    if not isinstance(pagination, Tag):
        return 1
    pages = []
    for a in pagination.find_all("a"):
        if not isinstance(a, Tag):
            continue
        match = re.search(r"[?&]page=(\d+)", _attr(a, "href") or "")
        if match:
            pages.append(int(match.group(1)))
    return max(pages) if pages else 1


def scrape(base_url: str, options: Optional[ScrapeOptions] = None) -> List[Dict[str, Any]]:
    options = options or ScrapeOptions()
    max_pages = options.max_pages or 300

    print(f"--- DealerSocket Gemini (Browser): {base_url} ---")
    results: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # "networkidle" times out on sites running chat widgets/trackers
        # that poll continuously and never let the network go idle (the
        # same issue dealerinspire.py hit and fixed the same way, confirmed
        # live on Acura of Fremont) -- wait_for_selector right after
        # already confirms real content loaded.
        page.goto(f"{base_url.rstrip('/')}/inventory/used", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(".clean-design-srp-card", timeout=15000)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        total_pages = min(_max_page_number(soup), max_pages)

        previous_page_vins: Optional[frozenset[str]] = None
        for page_num in range(1, total_pages + 1):
            print(f"--- Scraping Page {page_num}/{total_pages} ---")
            if page_num > 1:
                page.goto(
                    f"{base_url.rstrip('/')}/inventory/used?page={page_num}",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                page.wait_for_selector(".clean-design-srp-card", timeout=15000)
                html = page.content()
                soup = BeautifulSoup(html, "html.parser")

            cards = [c for c in soup.find_all("div", class_="clean-design-srp-card") if isinstance(c, Tag)]

            page_vins = [parse_item_id(_attr(c, "data-itemid") or "")["vin"] for c in cards]
            current_page_vins = frozenset(vin for vin in page_vins if vin)
            if page_did_not_advance(current_page_vins, previous_page_vins):
                print("Pagination did not advance (same vehicles as the previous page) -- stopping.")
                break
            previous_page_vins = current_page_vins

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

            # No documented Crawl-delay for this platform (unlike DealerOn's
            # explicit 10s) -- a modest delay between page fetches to stay
            # polite regardless.
            page.wait_for_timeout(2000)

        browser.close()

    return results
