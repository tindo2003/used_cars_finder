import requests
from bs4 import BeautifulSoup
import re


def extract_year_make_model(title):
    """
    Parses a string like '2023 GMC Savana 2500 Work Van'
    Returns: (2023, 'GMC', 'Savana')
    """
    # Look for 4-digit year at start
    year_match = re.match(r"^(199\d|20[0-2]\d)", title)
    year = int(year_match.group(1)) if year_match else 2010

    # Simple split: Year + Make + Model
    parts = title.replace(str(year), "").strip().split()
    make = parts[0] if len(parts) > 0 else "Unknown"
    model = parts[1] if len(parts) > 1 else "Unknown"

    return year, make, model


def scrape(base_url, make, model, max_price):
    print(f"--- DealerOn: {base_url} ---")
    results = []

    # DealerOn standard inventory URL
    url = f"{base_url}/searchused.aspx"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            return results

        soup = BeautifulSoup(res.text, "html.parser")

        # DealerOn containers often use these classes
        vehicles = soup.find_all("div", class_="vehicle-card")

        for v in vehicles:
            try:
                # 1. Get Title and Details
                title_elem = v.find("h2") or v.find("a", class_="url")
                if not title_elem:
                    continue
                title = title_elem.text.strip()

                # 2. Get Price
                price_elem = v.find("span", class_="internet-price") or v.find(
                    "span", class_="price"
                )
                price_str = (
                    price_elem.text.replace("$", "").replace(",", "")
                    if price_elem
                    else "0"
                )
                price = float(price_str)

                if max_price and price > max_price:
                    continue

                # 3. Get Image (handling relative paths)
                img_elem = v.find("img", class_="hero-carousel__image")
                photo_url = (
                    base_url + img_elem["src"]
                    if img_elem and img_elem.has_attr("src")
                    else None
                )

                # 4. Get Link
                link_elem = v.find("a", class_="view-details") or v.find(
                    "a", class_="url"
                )
                item_url = base_url + link_elem["href"] if link_elem else base_url

                # 5. Extract Year/Make/Model
                year, car_make, car_model = extract_year_make_model(title)

                results.append(
                    {
                        "marketplace_source": "dealeron",
                        "original_url": item_url,
                        "make": car_make,
                        "model": car_model,
                        "model_year": year,
                        "price": price,
                        "photos": [photo_url] if photo_url else [],
                    }
                )
            except Exception as e:
                continue

    except Exception as e:
        print(f"Error scraping DealerOn site {base_url}: {e}")

    return results
