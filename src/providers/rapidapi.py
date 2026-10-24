import re
from datetime import datetime
from typing import List, Optional
import httpx
from src.providers.base import AirbnbDataProvider
from src.models.schema import RawListing, RawCalendarDay
from config.settings import settings


class RapidApiAirbnbProvider(AirbnbDataProvider):
    """
    RapidAPI Airbnb Provider (using airbnb13 / airbnb-listings endpoints).
    Activates when RAPIDAPI_KEY is configured.
    """

    def __init__(self, api_key: Optional[str] = None, host: Optional[str] = None):
        self.api_key = api_key or settings.rapidapi_key
        self.host = host or settings.rapidapi_host
        self.base_url = f"https://{self.host}"
        self.headers = {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": self.host,
            "Accept": "application/json",
        }

    def get_provider_name(self) -> str:
        return "RAPIDAPI_AIRBNB13"

    def search_listings(self, area: str, page: int = 1, page_size: int = 20) -> List[RawListing]:
        if not self.api_key:
            return []

        url = f"{self.base_url}/search-location"
        params = {
            "location": f"{area}, Ahmedabad, Gujarat, India",
            "adults": "1",
            "page": str(page),
            "currency": "INR",
        }

        listings: List[RawListing] = []
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=self.headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", []) or data.get("data", [])
                    for item in results:
                        room_id = str(item.get("id") or item.get("room_id") or "")
                        if not room_id:
                            continue
                        
                        price_obj = item.get("price", {})
                        rate = price_obj.get("rate") or price_obj.get("total") or item.get("nightly_price")
                        
                        listings.append(
                            RawListing(
                                listing_id=room_id,
                                title=item.get("name") or item.get("title") or f"Stay in {area}",
                                area=area,
                                latitude=item.get("lat") or item.get("latitude"),
                                longitude=item.get("lng") or item.get("longitude"),
                                property_type=item.get("type") or item.get("property_type") or "Apartment",
                                room_type=item.get("room_type") or "Entire place",
                                bedrooms=item.get("bedrooms") or 1,
                                bathrooms=item.get("bathrooms") or 1.0,
                                rating=item.get("rating") or item.get("star_rating"),
                                review_count=item.get("reviewsCount") or item.get("reviews_count") or 0,
                                nightly_price=float(rate) if rate else None,
                                listing_url=f"https://www.airbnb.com/rooms/{room_id}",
                                source="RAPIDAPI_OBSERVED",
                            )
                        )
        except Exception:
            pass

        return listings

    def get_calendar(self, listing_id: str, horizon_days: int = 30) -> List[RawCalendarDay]:
        if not self.api_key:
            return []

        now = datetime.now()
        url = f"{self.base_url}/calendar"
        params = {
            "room_id": listing_id,
            "currency": "INR",
            "year": str(now.year),
            "month": str(now.month),
            "count": "2",
        }

        calendar_days: List[RawCalendarDay] = []
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=self.headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    months = data.get("calendar_months", []) or data.get("months", [])
                    for m in months:
                        for d in m.get("days", []):
                            date_str = d.get("date")
                            if not date_str:
                                continue
                            is_avail = bool(d.get("available"))
                            min_nights = int(d.get("min_nights") or d.get("minimum_stay") or 1)
                            
                            p_info = d.get("price", {})
                            price_val = None
                            if isinstance(p_info, dict):
                                price_val = p_info.get("local_price") or p_info.get("rate")
                            elif isinstance(p_info, (int, float)):
                                price_val = float(p_info)

                            calendar_days.append(
                                RawCalendarDay(
                                    listing_id=listing_id,
                                    calendar_date=date_str,
                                    status="available" if is_avail else "unavailable",
                                    bookable=is_avail,
                                    price=float(price_val) if price_val else None,
                                    minimum_stay=min_nights,
                                    raw_status=d.get("type") or ("AVAILABLE" if is_avail else "UNAVAILABLE"),
                                    source="RAPIDAPI_OBSERVED",
                                )
                            )
        except Exception:
            pass

        return calendar_days[:horizon_days]

    def get_listing_details(self, listing_id: str) -> Optional[RawListing]:
        return None
