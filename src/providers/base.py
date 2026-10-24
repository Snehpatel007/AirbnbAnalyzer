from abc import ABC, abstractmethod
from typing import List, Optional
from src.models.schema import RawListing, RawCalendarDay


class AirbnbDataProvider(ABC):
    """
    Abstract interface for all Airbnb data providers.
    Ensures provider-agnostic implementation throughout the system.
    """

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns the identifier name of this provider."""
        pass

    @abstractmethod
    def search_listings(self, area: str, page: int = 1, page_size: int = 20) -> List[RawListing]:
        """
        Search for listings in a specific area of Ahmedabad.
        Must return list of RawListing with stable listing_id.
        """
        pass

    @abstractmethod
    def get_calendar(self, listing_id: str, horizon_days: int = 30) -> List[RawCalendarDay]:
        """
        Retrieve calendar availability snapshot for the next `horizon_days`.
        Returns daily status (available, booked, blocked, unavailable).
        """
        pass

    @abstractmethod
    def get_listing_details(self, listing_id: str) -> Optional[RawListing]:
        """
        Fetch full details for an individual listing ID.
        """
        pass
