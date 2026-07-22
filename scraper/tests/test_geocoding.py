from typing import Any, List, Optional, Tuple

from geocoding import geocode, geocode_listings, haversine_miles, point_coordinates
from tests.fakes import FakeSupabase


class FakeResponse:
    def __init__(self, json_data: Any, status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code} error")

    def json(self) -> Any:
        return self._json_data


def make_listing(**overrides: Any) -> dict:
    listing = {
        "id": "listing-1",
        "status": "active",
        "city": "San Jose",
        "location": None,
    }
    listing.update(overrides)
    return listing


# --- geocode() ---


def test_geocode_returns_lat_lng_on_a_successful_match():
    result = geocode(
        "San Jose, CA, USA",
        http_get=lambda *a, **k: FakeResponse([{"lat": "37.3382", "lon": "-121.8863"}]),
    )

    assert result == (37.3382, -121.8863)


def test_geocode_returns_none_on_empty_results():
    # The real-world case: a Craigslist ad's location field scraped as
    # garbage (e.g. "+ Call (408) 831-3270") rather than a real place name.
    result = geocode("+ Call (408) 831-3270", http_get=lambda *a, **k: FakeResponse([]))

    assert result is None


def test_geocode_returns_none_on_a_non_2xx_response():
    result = geocode(
        "San Jose, CA, USA",
        http_get=lambda *a, **k: FakeResponse([], status_code=503),
    )

    assert result is None


def test_geocode_returns_none_on_a_request_exception():
    import requests

    def raise_connection_error(*args: Any, **kwargs: Any) -> Any:
        raise requests.ConnectionError("boom")

    result = geocode("San Jose, CA, USA", http_get=raise_connection_error)

    assert result is None


# --- geocode_listings() ---


def test_writes_correct_ewkt_with_lat_lng_in_the_right_order():
    # geocode() returns (lat, lng); PostGIS wants POINT(lng lat) -- this
    # is the easiest bug to introduce here, so assert the exact string.
    supabase = FakeSupabase(initial_data={"listings": [make_listing()]})

    updated = geocode_listings(
        supabase,
        geocode_fn=lambda query: (37.3382, -121.8863),
        sleep_fn=lambda seconds: None,
    )

    assert updated == 1
    assert supabase.table("listings").data[0]["location"] == "SRID=4326;POINT(-121.8863 37.3382)"


def test_skips_a_listing_that_already_has_a_location():
    calls: List[str] = []

    def recording_geocode(query: str) -> Tuple[float, float]:
        calls.append(query)
        return (0.0, 0.0)

    # location is read back through Listing.model_validate() (via
    # read_listings()), so this needs the real GeoJSON-dict shape
    # PostgREST actually returns for a geometry column -- not the EWKT
    # text geocode_listings() writes (see models.py's Listing.location).
    already_geocoded = {"type": "Point", "coordinates": [-121.8863, 37.3382]}
    supabase = FakeSupabase(initial_data={"listings": [make_listing(location=already_geocoded)]})

    updated = geocode_listings(supabase, geocode_fn=recording_geocode, sleep_fn=lambda seconds: None)

    assert updated == 0
    assert calls == []


def test_geocodes_a_distinct_city_only_once_across_multiple_listings():
    calls: List[str] = []

    def recording_geocode(query: str) -> Tuple[float, float]:
        calls.append(query)
        return (37.3382, -121.8863)

    supabase = FakeSupabase(
        initial_data={
            "listings": [
                make_listing(id="a", city="San Jose"),
                make_listing(id="b", city="San Jose"),
                make_listing(id="c", city="san jose  "),  # same city, different casing/whitespace
            ]
        }
    )

    updated = geocode_listings(supabase, geocode_fn=recording_geocode, sleep_fn=lambda seconds: None)

    assert updated == 3
    assert len(calls) == 1
    for row in supabase.table("listings").data:
        assert row["location"] == "SRID=4326;POINT(-121.8863 37.3382)"


def test_leaves_location_null_and_continues_when_geocode_fails_for_one_listing():
    supabase = FakeSupabase(
        initial_data={
            "listings": [
                make_listing(id="bad", city="+ Call (408) 831-3270"),
                make_listing(id="good", city="Fremont"),
            ]
        }
    )

    def fake_geocode(query: str) -> Optional[Tuple[float, float]]:
        return None if "Call" in query else (37.5485, -121.9886)

    updated = geocode_listings(supabase, geocode_fn=fake_geocode, sleep_fn=lambda seconds: None)

    assert updated == 1
    rows = {row["id"]: row for row in supabase.table("listings").data}
    assert rows["bad"]["location"] is None
    assert rows["good"]["location"] == "SRID=4326;POINT(-121.9886 37.5485)"


def test_continues_processing_when_one_listings_write_fails(monkeypatch: Any):
    supabase = FakeSupabase(
        initial_data={
            "listings": [
                make_listing(id="fails-to-write", city="San Jose"),
                make_listing(id="writes-fine", city="Fremont"),
            ]
        }
    )

    from db import DbClient

    real_update = DbClient.update

    def flaky_update(self: DbClient, match: dict, fields: dict) -> Any:
        if match.get("id") == "fails-to-write":
            raise RuntimeError("simulated write failure")
        return real_update(self, match, fields)

    monkeypatch.setattr(DbClient, "update", flaky_update)

    updated = geocode_listings(
        supabase,
        geocode_fn=lambda query: (37.3382, -121.8863),
        sleep_fn=lambda seconds: None,
    )

    assert updated == 1
    rows = {row["id"]: row for row in supabase.table("listings").data}
    assert rows["writes-fine"]["location"] == "SRID=4326;POINT(-121.8863 37.3382)"


def test_sleep_fn_called_once_per_distinct_city_not_once_per_listing():
    sleep_calls = []
    supabase = FakeSupabase(
        initial_data={
            "listings": [
                make_listing(id="a", city="San Jose"),
                make_listing(id="b", city="San Jose"),
                make_listing(id="c", city="Fremont"),
            ]
        }
    )

    geocode_listings(
        supabase,
        geocode_fn=lambda query: (0.0, 0.0),
        sleep_fn=lambda seconds: sleep_calls.append(seconds),
    )

    assert len(sleep_calls) == 2  # one per distinct city (San Jose, Fremont), not per listing


def test_only_geocodes_currently_active_listings():
    supabase = FakeSupabase(
        initial_data={"listings": [make_listing(id="inactive", status="expired")]}
    )

    updated = geocode_listings(
        supabase,
        geocode_fn=lambda query: (37.3382, -121.8863),
        sleep_fn=lambda seconds: None,
    )

    assert updated == 0
    assert supabase.table("listings").data[0]["location"] is None


# --- point_coordinates() ---


def test_point_coordinates_extracts_lat_lng_in_the_right_order():
    # GeoJSON orders coordinates [lng, lat] -- point_coordinates() must
    # flip these to match this module's (lat, lng) convention. This is
    # the same class of order-swap bug as geocode_listings' EWKT writing.
    point = {"type": "Point", "coordinates": [-121.8863, 37.3382]}

    assert point_coordinates(point) == (37.3382, -121.8863)


def test_point_coordinates_returns_none_for_none():
    assert point_coordinates(None) is None


def test_point_coordinates_returns_none_for_a_non_point_geometry():
    assert point_coordinates({"type": "LineString", "coordinates": [[0, 0], [1, 1]]}) is None


def test_point_coordinates_returns_none_for_malformed_coordinates():
    assert point_coordinates({"type": "Point", "coordinates": [1.0]}) is None
    assert point_coordinates({"type": "Point", "coordinates": ["not", "numbers"]}) is None
    assert point_coordinates({"type": "Point"}) is None


# --- haversine_miles() ---


def test_haversine_miles_zero_distance_for_the_same_point():
    assert haversine_miles(37.3382, -121.8863, 37.3382, -121.8863) == 0.0


def test_haversine_miles_known_bay_area_distance():
    # San Jose to Fremont, roughly 20 miles apart -- loose tolerance since
    # this is a sanity check on the formula, not a precision requirement.
    san_jose = (37.3382, -121.8863)
    fremont = (37.5485, -121.9886)

    distance = haversine_miles(*san_jose, *fremont)

    assert 15 < distance < 25
