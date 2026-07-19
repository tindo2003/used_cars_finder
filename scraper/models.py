"""
Pydantic models for the two shapes this codebase passes around the most:
a scraped/stored car listing, and a saved search to match it against.
Real data is inconsistent by source (Craigslist has no VIN/mileage/
transmission; DealerInspire doesn't expose mileage/transmission at all
-- see providers/dealerinspire.py), so every field is optional rather
than requiring a shape no single source actually produces.

Deliberately NOT used by providers/*.py or runner.py -- those keep
returning/passing plain dicts exactly as before. Validation happens at
the DB boundary (db.py's bulk_save/upsert and read_listings), which is
the earliest point *shared* by every source, without touching each
scraper individually. See research/mvp-checklist.md for the reasoning.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class Listing(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    vin: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    model_year: Optional[int] = None
    price: Optional[float] = None
    mileage: Optional[int] = None
    transmission: Optional[str] = None
    seller_type: Optional[str] = None
    fuel_type: Optional[str] = None
    city: Optional[str] = None
    dealer_name: Optional[str] = None
    marketplace_source: Optional[str] = None
    original_url: Optional[str] = None
    posted_at: Optional[str] = None
    photos: List[str] = Field(default_factory=list)
    status: Optional[str] = None
    deal_score: Optional[float] = None
    is_good_deal: Optional[bool] = None
    duplicate_of: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class SavedSearch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    user_id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    make: Optional[List[str]] = None
    model: Optional[List[str]] = None
    min_year: Optional[int] = None
    max_mileage: Optional[int] = None
    max_price: Optional[float] = None
    transmission: Optional[str] = None
    seller_type: Optional[str] = None
    search_radius_miles: Optional[float] = None
    target_location: Optional[str] = None
    notification_grouping: Optional[str] = "combined"
    created_at: Optional[datetime] = None
