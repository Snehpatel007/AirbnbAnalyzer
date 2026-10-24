from typing import List, Dict, Tuple, Set
from datetime import datetime
from src.models.schema import RawListing, RawCalendarDay


from config.settings import settings


class DataQualityValidator:
    """
    Validates data quality before and after database ingestion.
    Enforces rules:
    - Global listing filters (2+ bedrooms, 2+ beds, wifi, air conditioning)
    - Duplicate listing IDs
    - Missing listing IDs
    - Missing area
    - Invalid prices
    - Invalid calendar dates
    - Duplicate listing/date observations
    - Coverage calculation
    """

    @staticmethod
    def validate_listings(listings: List[RawListing]) -> Tuple[List[RawListing], List[str]]:
        valid: List[RawListing] = []
        errors: List[str] = []
        seen_ids: Set[str] = set()
        filters = settings.market_config.global_filters

        for idx, l in enumerate(listings):
            if not l.listing_id or not str(l.listing_id).strip():
                errors.append(f"Row {idx}: Missing listing_id")
                continue

            lid = str(l.listing_id).strip()
            if lid in seen_ids:
                errors.append(f"Duplicate listing_id encountered: {lid}")
                continue
            seen_ids.add(lid)

            if not l.area or not l.area.strip():
                errors.append(f"Listing {lid}: Missing area")
                continue

            # Global Filters Enforced:
            if l.bedrooms < filters.min_bedrooms:
                errors.append(f"Listing {lid}: Below min_bedrooms ({l.bedrooms} < {filters.min_bedrooms})")
                continue
            if l.beds < filters.min_beds:
                errors.append(f"Listing {lid}: Below min_beds ({l.beds} < {filters.min_beds})")
                continue
            if filters.requires_wifi and not l.has_wifi:
                errors.append(f"Listing {lid}: Missing required WiFi amenity")
                continue
            if filters.requires_air_conditioning and not l.has_ac:
                errors.append(f"Listing {lid}: Missing required Air Conditioning amenity")
                continue

            if l.nightly_price is not None and l.nightly_price < 0:
                errors.append(f"Listing {lid}: Invalid negative price {l.nightly_price}")
                l.nightly_price = None

            valid.append(l)

        return valid, errors

    @staticmethod
    def validate_calendar_days(
        days: List[RawCalendarDay], observation_date: str
    ) -> Tuple[List[RawCalendarDay], List[str]]:
        valid: List[RawCalendarDay] = []
        errors: List[str] = []
        seen_keys: Set[str] = set()

        try:
            obs_dt = datetime.strptime(observation_date, "%Y-%m-%d")
        except ValueError:
            return [], [f"Invalid observation_date format: {observation_date}"]

        for idx, d in enumerate(days):
            if not d.listing_id:
                errors.append(f"Day {idx}: Missing listing_id")
                continue

            try:
                cal_dt = datetime.strptime(d.calendar_date, "%Y-%m-%d")
                if cal_dt < obs_dt:
                    errors.append(f"Listing {d.listing_id}: Calendar date {d.calendar_date} is in the past")
                    continue
            except ValueError:
                errors.append(f"Listing {d.listing_id}: Invalid calendar date format: {d.calendar_date}")
                continue

            obs_key = f"{d.listing_id}_{d.calendar_date}_{observation_date}"
            if obs_key in seen_keys:
                errors.append(f"Duplicate observation record for listing {d.listing_id} on {d.calendar_date}")
                continue
            seen_keys.add(obs_key)

            if d.price is not None and d.price < 0:
                errors.append(f"Listing {d.listing_id}: Negative price {d.price} on {d.calendar_date}")
                d.price = None

            valid.append(d)

        return valid, errors
