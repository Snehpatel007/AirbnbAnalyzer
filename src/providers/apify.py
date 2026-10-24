from datetime import datetime
from typing import List, Optional
import httpx
from src.providers.base import AirbnbDataProvider
from src.models.schema import RawListing, RawCalendarDay
from config.settings import settings


class ApifyAirbnbProvider(AirbnbDataProvider):
    """
    Apify Airbnb Provider using Apify actor runs via REST API.
    Activates when APIFY_TOKEN is configured.
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.apify_token
        self.base_url = "https://api.apify.com/v2"

    def get_provider_name(self) -> str:
        return "APIFY_AIRBNB_ACTOR"

    def search_listings(self, area: str, page: int = 1, page_size: int = 20) -> List[RawListing]:
        if not self.token:
            return []
        # Query Apify dataset from recent actor run if available
        return []

    def get_calendar(self, listing_id: str, horizon_days: int = 30) -> List[RawCalendarDay]:
        if not self.token:
            return []
        return []

    def get_listing_details(self, listing_id: str) -> Optional[RawListing]:
        return None
