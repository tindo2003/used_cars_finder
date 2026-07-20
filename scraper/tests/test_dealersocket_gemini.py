from bs4 import BeautifulSoup, Tag

from providers.dealersocket_gemini import (
    extract_details,
    extract_mileage,
    extract_price,
    extract_vehicle_data,
    parse_item_id,
)


def test_parse_item_id_simple_make_and_model():
    assert parse_item_id("Kia-Forte-LXS-3KPF24AD5PE553158") == {
        "make": "Kia",
        "model": "Forte",
        "trim": "LXS",
        "vin": "3KPF24AD5PE553158",
    }


def test_parse_item_id_model_contains_a_hyphen():
    # "CR-V" is the real model name -- not "CR" with model "V".
    assert parse_item_id("Honda-CR-V-LX-JHLRD68423C003512") == {
        "make": "Honda",
        "model": "CR-V",
        "trim": "LX",
        "vin": "JHLRD68423C003512",
    }


def test_parse_item_id_make_contains_a_hyphen():
    # "Mercedes-Benz" is the real make -- not "Mercedes" with model "Benz".
    assert parse_item_id("Mercedes-Benz-CLA-CLA 250-WDDSJ4EB0HN432003") == {
        "make": "Mercedes-Benz",
        "model": "CLA",
        "trim": "CLA 250",
        "vin": "WDDSJ4EB0HN432003",
    }


def test_parse_item_id_multi_word_model():
    assert parse_item_id("Jeep-Grand Cherokee-Limited-1C4RJFBG1GC307820") == {
        "make": "Jeep",
        "model": "Grand Cherokee",
        "trim": "Limited",
        "vin": "1C4RJFBG1GC307820",
    }


def test_parse_item_id_too_few_segments_returns_all_none():
    assert parse_item_id("JustAVin") == {"make": None, "model": None, "trim": None, "vin": None}


def _card(html: str) -> Tag:
    soup = BeautifulSoup(html, "html.parser")
    found = soup.find("div")
    assert isinstance(found, Tag)
    return found


def test_extract_price_reads_the_dollar_amount():
    card = _card(
        '<div><div class="vehicle-summary-price">Your Price<span>$5,835</span></div></div>'
    )
    assert extract_price(card) == 5835.0


def test_extract_price_missing_defaults_to_zero():
    card = _card("<div></div>")
    assert extract_price(card) == 0.0


def test_extract_details_reads_label_value_rows():
    card = _card(
        """
        <div>
          <div class="details-item-row">
            <div class="details-item-label">Mileage</div>
            <div class="details-item-value">186,105 Miles</div>
          </div>
          <div class="details-item-row">
            <div class="details-item-label">Drivetrain</div>
            <div class="details-item-value">FWD</div>
          </div>
        </div>
        """
    )
    assert extract_details(card) == {"mileage": "186,105 Miles", "drivetrain": "FWD"}


def test_extract_mileage_parses_digits_out_of_the_text():
    assert extract_mileage({"mileage": "186,105 Miles"}) == 186105


def test_extract_mileage_missing_returns_none():
    assert extract_mileage({}) is None


def test_extract_vehicle_data_full_card():
    card = _card(
        """
        <div class="clean-design-srp-card" data-itemid="Honda-CR-V-LX-JHLRD68423C003512">
          <a class="srp-vehicle-box" href="https://example.com/viewdetails/used/honda-cr-v"></a>
          <img class="srp-vehiclebox-image" src="/photos/cr-v.jpg" alt="2003 Honda CR-V" />
          <h2 class="vehiclebox-title-main">2003 Honda CR-V LX FWD</h2>
          <div class="vehicle-summary-price">Your Price<span>$5,835</span></div>
          <div class="details-item-row">
            <div class="details-item-label">Mileage</div>
            <div class="details-item-value">186,105 Miles</div>
          </div>
        </div>
        """
    )

    result = extract_vehicle_data(card, "https://example.com", city="Fremont", dealer_name="Winn Kia of Fremont")

    assert result == {
        "marketplace_source": "dealersocket-gemini",
        "original_url": "https://example.com/viewdetails/used/honda-cr-v",
        "vin": "JHLRD68423C003512",
        "make": "Honda",
        "model": "CR-V",
        "trim": "LX",
        "model_year": 2003,
        "price": 5835.0,
        "mileage": 186105,
        "seller_type": "dealer",
        "transmission": None,
        "fuel_type": None,
        "city": "Fremont",
        "dealer_name": "Winn Kia of Fremont",
        "posted_at": None,
        "photos": ["https://example.com/photos/cr-v.jpg"],
    }


def test_extract_vehicle_data_missing_itemid_falls_back_to_unknown():
    card = _card('<div class="clean-design-srp-card"></div>')

    result = extract_vehicle_data(card, "https://example.com")

    assert result is not None
    assert result["make"] == "Unknown"
    assert result["model"] == "Unknown"
    assert result["vin"] is None
