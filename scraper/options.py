from dataclasses import dataclass
from typing import Optional


@dataclass
class ScrapeOptions:
    """
    Shared config passed to every provider's scrape(). Add new fields here
    as filters/behaviors are needed instead of growing each provider's
    positional argument list.
    """

    make: Optional[str] = None
    model: Optional[str] = None
    max_price: Optional[float] = None
    max_pages: Optional[int] = None
    city: Optional[str] = None
