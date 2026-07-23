from bs4 import BeautifulSoup, Tag

from providers.dealerdotcom import extract_vehicle_data, parse_json_ld_offers

CARD_HTML = """
<li class="vehicle-card vehicle-card-detailed">
  <h2 class="vehicle-card-title"><a href="/used/Subaru/2024-Subaru-Crosstrek-for-sale-fremont-ca-abc123.htm?priorityType=spv"><span>2024 Subaru Crosstrek Premium</span></a></h2>
  <div class="vehicle-card-highlight">
    <div class="highlight-badge hotcars">Hot Vehicle</div>
    <div class="highlight-badge default">32,373 miles</div>
  </div>
  <dl class="pricing-detail">
    <dt class="ABCRule"><span class="price-label">Administration Fee</span></dt>
    <dd class="ABCRule"><span class="price-value">$85</span></dd>
    <dt class="final-price internetPrice"><span class="price-label">Our Price</span></dt>
    <dd class="final-price internetPrice"><span class="price-value">$24,606</span></dd>
  </dl>
  <img src="/photos/crosstrek.jpg" />
</li>
"""

JSON_LD_HTML = """
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "CollectionPage",
  "about": {
    "offers": {
      "itemOffered": [
        {
          "url": "https://example.com/used/Subaru/2024-Subaru-Crosstrek-for-sale-fremont-ca-abc123.htm",
          "name": "Used 2024 Subaru Crosstrek Premium",
          "vehicleIdentificationNumber": "JF2GUADC1RH257844",
          "brand": {"name": "Subaru"},
          "model": "Crosstrek",
          "vehicleModelDate": 2024,
          "vehicleTransmission": "Lineartronic CVT",
          "fuelType": "Gasoline",
          "offers": {"price": "24606"},
          "image": "https://example.com/photos/crosstrek-real.jpg",
          "mileageFromOdometer": {"value": 32, "unitCode": "SMI"}
        }
      ]
    }
  }
}
</script>
"""


def _card(html: str) -> Tag:
    soup = BeautifulSoup(html, "html.parser")
    found = soup.find("li")
    assert isinstance(found, Tag)
    return found


def test_parse_json_ld_offers_keyed_by_url_path():
    offers = parse_json_ld_offers(JSON_LD_HTML)
    assert list(offers.keys()) == ["/used/Subaru/2024-Subaru-Crosstrek-for-sale-fremont-ca-abc123.htm"]
    assert offers["/used/Subaru/2024-Subaru-Crosstrek-for-sale-fremont-ca-abc123.htm"]["vehicleIdentificationNumber"] == "JF2GUADC1RH257844"


def test_parse_json_ld_offers_no_matching_script_returns_empty():
    assert parse_json_ld_offers("<html><body>no json-ld here</body></html>") == {}


def test_parse_json_ld_offers_malformed_json_is_skipped_not_raised():
    assert parse_json_ld_offers('<script type="application/ld+json">{not valid json</script>') == {}


def test_extract_vehicle_data_prefers_json_ld_over_card_text():
    card = _card(CARD_HTML)
    json_ld_offers = parse_json_ld_offers(JSON_LD_HTML)

    result = extract_vehicle_data(
        card, "https://example.com", json_ld_offers, city="Fremont", dealer_name="Premier Subaru of Fremont"
    )

    assert result == {
        "marketplace_source": "dealerdotcom",
        "original_url": "https://example.com/used/Subaru/2024-Subaru-Crosstrek-for-sale-fremont-ca-abc123.htm?priorityType=spv",
        "vin": "JF2GUADC1RH257844",
        "make": "Subaru",
        "model": "Crosstrek",
        "trim": "Premium",
        "model_year": 2024,
        "price": 24606.0,
        # Mileage always comes from the card, never the JSON-LD blob (its
        # mileageFromOdometer.value is truncated to thousands -- confirmed
        # live, "32" for a real 32,373-mile car) -- this is the regression
        # test for that specific bug.
        "mileage": 32373,
        "seller_type": "dealer",
        "transmission": "Lineartronic CVT",
        "fuel_type": "Gasoline",
        "city": "Fremont",
        "dealer_name": "Premier Subaru of Fremont",
        "posted_at": None,
        # JSON-LD's own image URL wins over the card's -- confirmed live
        # they're the same underlying photo, JSON-LD's is just already absolute.
        "photos": ["https://example.com/photos/crosstrek-real.jpg"],
    }


def test_extract_vehicle_data_falls_back_to_card_text_with_no_json_ld_match():
    card = _card(CARD_HTML)

    result = extract_vehicle_data(card, "https://example.com", json_ld_offers={})

    assert result is not None
    assert result["vin"] is None  # no VIN available anywhere on the card itself
    assert result["make"] == "Subaru"
    assert result["model"] == "Crosstrek Premium"  # no clean model/trim split without JSON-LD
    assert result["trim"] is None
    assert result["model_year"] == 2024
    assert result["price"] == 24606.0  # still reads the card's own final-price
    assert result["mileage"] == 32373
    assert result["transmission"] is None
    assert result["fuel_type"] is None
    assert result["photos"] == ["https://example.com/photos/crosstrek.jpg"]


def test_extract_vehicle_data_only_reads_the_final_price_not_the_admin_fee():
    # The admin-fee row also has class "ABCRule" with its own $ amount --
    # must not be mistaken for the real price, in the no-JSON-LD fallback path.
    card = _card(
        """
        <li class="vehicle-card vehicle-card-detailed">
          <h2 class="vehicle-card-title"><a href="/x.htm"><span>2020 Toyota Camry</span></a></h2>
          <dl class="pricing-detail">
            <dt class="ABCRule"><span class="price-label">Administration Fee</span></dt>
            <dd class="ABCRule"><span class="price-value">$85</span></dd>
            <dt class="final-price internetPrice"><span class="price-label">Our Price</span></dt>
            <dd class="final-price internetPrice"><span class="price-value">$18,000</span></dd>
          </dl>
        </li>
        """
    )
    result = extract_vehicle_data(card, "https://example.com")
    assert result is not None
    assert result["price"] == 18000.0


def test_extract_vehicle_data_trim_falls_back_to_none_when_model_not_found_in_name():
    # Defensive case: if a future template change makes `name` not
    # actually contain `model` as a substring, trim extraction should
    # degrade to None rather than raising or producing garbage.
    json_ld_html = """
    <script type="application/ld+json">
    {"about": {"offers": {"itemOffered": [{
        "url": "https://example.com/used/Subaru/x.htm",
        "name": "Something unexpected entirely",
        "brand": {"name": "Subaru"},
        "model": "Crosstrek",
        "vehicleModelDate": 2024,
        "offers": {"price": "24606"}
    }]}}}
    </script>
    """
    card = _card(
        """
        <li class="vehicle-card vehicle-card-detailed">
          <h2 class="vehicle-card-title"><a href="/used/Subaru/x.htm"><span>2024 Subaru Crosstrek</span></a></h2>
        </li>
        """
    )
    json_ld_offers = parse_json_ld_offers(json_ld_html)

    result = extract_vehicle_data(card, "https://example.com", json_ld_offers)

    assert result is not None
    assert result["trim"] is None
    assert result["model"] == "Crosstrek"


def test_extract_vehicle_data_empty_card_falls_back_to_unknown():
    card = _card('<li class="vehicle-card vehicle-card-detailed"></li>')

    result = extract_vehicle_data(card, "https://example.com")

    assert result is not None
    assert result["make"] == "Unknown"
    assert result["model"] == "Unknown"
    assert result["model_year"] == 0
    assert result["vin"] is None
    assert result["mileage"] is None
    assert result["photos"] == []
