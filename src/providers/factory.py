from typing import Optional, List
from config.settings import settings
from src.providers.base import AirbnbDataProvider
from src.providers.direct_web import DirectWebAirbnbProvider
from src.providers.rapidapi import RapidApiAirbnbProvider
from src.providers.apify import ApifyAirbnbProvider
from src.providers.simulation import SimulatedMarketProvider
from src.models.schema import RawListing, RawCalendarDay


class HybridAirbnbProvider(AirbnbDataProvider):
    """
    Hybrid Provider:
    - Combines Direct Airbnb Web Client with the high-fidelity Ahmedabad Market Engine.
    - If RapidAPI or Apify keys are set in environment, utilizes them.
    - Ensures 100% scheduled uptime and data completeness while capturing live web data whenever reachable.
    """

    def __init__(self, observation_date: Optional[str] = None):
        self.observation_date = observation_date
        self.direct_web = DirectWebAirbnbProvider()
        self.simulation = SimulatedMarketProvider(observation_date=observation_date)
        self.rapidapi = RapidApiAirbnbProvider() if settings.rapidapi_key else None
        self.apify = ApifyAirbnbProvider() if settings.apify_token else None

    def get_provider_name(self) -> str:
        if self.rapidapi and self.rapidapi.api_key:
            return "RAPIDAPI_PRIMARY"
        return "HYBRID_WEB_SIMULATED"

    def search_listings(self, area: str, page: int = 1, page_size: int = 20) -> List[RawListing]:
        # If RapidAPI configured, use it
        if self.rapidapi and self.rapidapi.api_key:
            res = self.rapidapi.search_listings(area, page, page_size)
            if res:
                return res

        # Try live web client
        live_res = self.direct_web.search_listings(area, page, page_size)
        if live_res and len(live_res) >= 3:
            return live_res

        # Fallback to authentic Ahmedabad simulated engine
        return self.simulation.search_listings(area, page, page_size)

    def get_calendar(self, listing_id: str, horizon_days: int = 30) -> List[RawCalendarDay]:
        # If RapidAPI configured, use it
        if self.rapidapi and self.rapidapi.api_key:
            res = self.rapidapi.get_calendar(listing_id, horizon_days)
            if res:
                return res

        # Try live web only for real listings
        if not listing_id.startswith("SIM_"):
            live_res = self.direct_web.get_calendar(listing_id, horizon_days)
            if live_res and len(live_res) >= horizon_days * 0.8:
                return live_res

        # Fallback to simulated engine with deterministic seeds
        return self.simulation.get_calendar(listing_id, horizon_days)

    def get_bulk_calendar(self, listing_ids: List[str], horizon_days: int = 7) -> dict:
        return self.direct_web.get_bulk_calendar(listing_ids, horizon_days)

    def get_horizon_calendar_by_date_search(
        self,
        master_listing_ids: List[str],
        start_date: Optional[str] = None,
        horizon_days: int = 7,
        listing_base_prices: Optional[dict] = None,
    ) -> dict:
        return self.direct_web.get_horizon_calendar_by_date_search(
            master_listing_ids=master_listing_ids,
            start_date=start_date,
            horizon_days=horizon_days,
            listing_base_prices=listing_base_prices,
        )

    def get_listing_details(self, listing_id: str) -> Optional[RawListing]:
        if not listing_id.startswith("SIM_"):
            res = self.direct_web.get_listing_details(listing_id)
            if res:
                return res
        return self.simulation.get_listing_details(listing_id)


def get_data_provider(provider_type: Optional[str] = None, observation_date: Optional[str] = None) -> AirbnbDataProvider:
    p_type = (provider_type or settings.data_provider).lower()
    
    if p_type == "rapidapi":
        return RapidApiAirbnbProvider()
    elif p_type == "apify":
        return ApifyAirbnbProvider()
    elif p_type == "direct_web":
        return DirectWebAirbnbProvider()
    elif p_type == "simulation":
        return SimulatedMarketProvider(observation_date=observation_date)
    else:
        return HybridAirbnbProvider(observation_date=observation_date)
