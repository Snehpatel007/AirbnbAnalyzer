from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class RawListing(BaseModel):
    listing_id: str
    title: Optional[str] = None
    area: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    property_type: Optional[str] = "Apartment"
    room_type: Optional[str] = "Entire place"
    bedrooms: int = 2
    beds: int = 2
    bathrooms: float = 1.0
    has_wifi: bool = True
    has_ac: bool = True
    rating: Optional[float] = None
    review_count: int = 0
    nightly_price: Optional[float] = None  # Base nightly rate if present in search
    listing_url: Optional[str] = None      # Direct Airbnb listing URL
    source: str = "AIRBNB_OBSERVED"


class RawCalendarDay(BaseModel):
    listing_id: str
    calendar_date: str  # YYYY-MM-DD
    status: str  # available, booked, blocked, unavailable, unknown
    bookable: bool = False
    price: Optional[float] = None
    minimum_stay: int = 1
    raw_status: Optional[str] = None
    source: str = "AIRBNB_OBSERVED"


class AreaSummary(BaseModel):
    area: str
    active_listings: int
    observed_unavailability_rate: float
    adr: float
    revpar_proxy: float
    booking_occupancy: Optional[float] = None
    change_7d_listings: int = 0
    change_30d_listings: int = 0
    change_7d_unavailability_pp: float = 0.0
    change_30d_unavailability_pp: float = 0.0
    coverage_rate: float = 1.0
    status: str = "COMPLETE"


class DailyMarketOverview(BaseModel):
    city: str
    observation_date: str
    active_listings: int
    observed_unavailability_rate: float
    adr: float
    revpar_proxy: float
    booking_occupancy: Optional[float] = None
    change_1d_listings: int = 0
    change_7d_listings: int = 0
    change_30d_listings: int = 0
    change_1d_unavailability_pp: float = 0.0
    change_7d_unavailability_pp: float = 0.0
    change_30d_unavailability_pp: float = 0.0
    coverage_rate: float
    status: str
    areas: List[AreaSummary]


class TrendPoint(BaseModel):
    date: str
    active_listings: int
    observed_unavailability_rate: float
    adr: float
    revpar_proxy: float
    coverage_rate: float


class NaturalLanguageQueryRequest(BaseModel):
    query: str
    area: Optional[str] = None
    date_range_days: int = 30


class NaturalLanguageQueryResponse(BaseModel):
    query: str
    answer: str
    metrics_used: Dict[str, Any]
    sources: List[str]
