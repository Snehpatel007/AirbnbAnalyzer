import hashlib
import random
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from src.providers.base import AirbnbDataProvider
from src.models.schema import RawListing, RawCalendarDay


# Realistic area profiles for Ahmedabad
# Realistic area profiles for all 40 production areas across Ahmedabad
AREA_PROFILES: Dict[str, Dict] = {
    # West / Prime Commercial & Residential
    "SG Highway": {"base_listings": 220, "base_adr": 4200.0, "adr_std": 650.0, "base_unavailability": 0.54, "lat": 23.0450, "lng": 72.5200, "property_types": ["Corporate executive suite", "Serviced apartment", "Modern flat"], "avg_rating": 4.82},
    "Thaltej": {"base_listings": 150, "base_adr": 4400.0, "adr_std": 700.0, "base_unavailability": 0.52, "lat": 23.0630, "lng": 72.5085, "property_types": ["Luxury apartment", "Serviced villa", "Entire home"], "avg_rating": 4.85},
    "Bodakdev": {"base_listings": 130, "base_adr": 4650.0, "adr_std": 750.0, "base_unavailability": 0.53, "lat": 23.0410, "lng": 72.5180, "property_types": ["Luxury condominium", "Boutique apartment", "Serviced penthouse"], "avg_rating": 4.87},
    "Satellite": {"base_listings": 160, "base_adr": 3950.0, "adr_std": 550.0, "base_unavailability": 0.51, "lat": 23.0270, "lng": 72.5270, "property_types": ["Entire apartment", "Modern 2BHK flat", "Residential home"], "avg_rating": 4.79},
    "Prahlad Nagar": {"base_listings": 175, "base_adr": 4350.0, "adr_std": 600.0, "base_unavailability": 0.55, "lat": 23.0120, "lng": 72.5110, "property_types": ["Boutique apartment", "Business stay condo", "Premium suite"], "avg_rating": 4.84},
    "Vastrapur": {"base_listings": 140, "base_adr": 4100.0, "adr_std": 580.0, "base_unavailability": 0.52, "lat": 23.0360, "lng": 72.5290, "property_types": ["Modern apartment", "Executive suite", "Studio flat"], "avg_rating": 4.80},
    "Sola": {"base_listings": 95, "base_adr": 3550.0, "adr_std": 480.0, "base_unavailability": 0.49, "lat": 23.0810, "lng": 72.5250, "property_types": ["Entire apartment", "Gated society flat"], "avg_rating": 4.75},
    "Science City": {"base_listings": 80, "base_adr": 3850.0, "adr_std": 520.0, "base_unavailability": 0.48, "lat": 23.0900, "lng": 72.5050, "property_types": ["Residential home", "Modern condo", "Entire villa"], "avg_rating": 4.78},
    "Sindhu Bhavan Road": {"base_listings": 110, "base_adr": 5200.0, "adr_std": 950.0, "base_unavailability": 0.56, "lat": 23.0450, "lng": 72.4950, "property_types": ["Luxury penthouse", "High-end serviced flat", "Boutique suite"], "avg_rating": 4.90},
    "Shilaj": {"base_listings": 70, "base_adr": 4800.0, "adr_std": 900.0, "base_unavailability": 0.51, "lat": 23.0645, "lng": 72.4740, "property_types": ["Entire villa", "Luxury bungalow", "Penthouse flat"], "avg_rating": 4.88},
    "Gota": {"base_listings": 120, "base_adr": 3200.0, "adr_std": 420.0, "base_unavailability": 0.47, "lat": 23.1040, "lng": 72.5350, "property_types": ["High-rise apartment", "Modern 2BHK flat"], "avg_rating": 4.72},

    # South-West / New Ahmedabad
    "Bopal": {"base_listings": 155, "base_adr": 3600.0, "adr_std": 480.0, "base_unavailability": 0.50, "lat": 23.0330, "lng": 72.4630, "property_types": ["Entire apartment", "Condominium", "Serviced apartment"], "avg_rating": 4.80},
    "South Bopal": {"base_listings": 140, "base_adr": 3500.0, "adr_std": 450.0, "base_unavailability": 0.49, "lat": 23.0185, "lng": 72.4705, "property_types": ["Entire apartment", "High-rise condo", "Modern flat"], "avg_rating": 4.77},
    "Ghuma": {"base_listings": 95, "base_adr": 3100.0, "adr_std": 400.0, "base_unavailability": 0.46, "lat": 23.0305, "lng": 72.4410, "property_types": ["Entire apartment", "Residential home", "Gated society flat"], "avg_rating": 4.70},
    "Shela": {"base_listings": 125, "base_adr": 3800.0, "adr_std": 550.0, "base_unavailability": 0.50, "lat": 23.0110, "lng": 72.4550, "property_types": ["Gated community flat", "Entire apartment", "Modern studio"], "avg_rating": 4.83},
    "Ambli": {"base_listings": 65, "base_adr": 5400.0, "adr_std": 1050.0, "base_unavailability": 0.54, "lat": 23.0430, "lng": 72.4830, "property_types": ["Luxury villa", "Designer suite", "Exclusive penthouse"], "avg_rating": 4.91},
    "Makarba": {"base_listings": 90, "base_adr": 3400.0, "adr_std": 450.0, "base_unavailability": 0.48, "lat": 23.0030, "lng": 72.5010, "property_types": ["Corporate apartment", "Modern flat"], "avg_rating": 4.74},
    "Jodhpur": {"base_listings": 85, "base_adr": 3700.0, "adr_std": 500.0, "base_unavailability": 0.50, "lat": 23.0190, "lng": 72.5240, "property_types": ["Entire apartment", "Residential flat"], "avg_rating": 4.78},
    "Sarkhej": {"base_listings": 70, "base_adr": 2900.0, "adr_std": 380.0, "base_unavailability": 0.45, "lat": 22.9850, "lng": 72.5000, "property_types": ["Budget apartment", "Entire home"], "avg_rating": 4.68},

    # Central Ahmedabad
    "Navrangpura": {"base_listings": 115, "base_adr": 4200.0, "adr_std": 620.0, "base_unavailability": 0.53, "lat": 23.0370, "lng": 72.5560, "property_types": ["Central executive flat", "Boutique apartment"], "avg_rating": 4.82},
    "CG Road": {"base_listings": 90, "base_adr": 4400.0, "adr_std": 650.0, "base_unavailability": 0.55, "lat": 23.0320, "lng": 72.5600, "property_types": ["Commercial hub apartment", "Business suite"], "avg_rating": 4.85},
    "Paldi": {"base_listings": 85, "base_adr": 3600.0, "adr_std": 480.0, "base_unavailability": 0.49, "lat": 23.0120, "lng": 72.5630, "property_types": ["Entire apartment", "Residential flat"], "avg_rating": 4.76},
    "Ambawadi": {"base_listings": 75, "base_adr": 4100.0, "adr_std": 580.0, "base_unavailability": 0.52, "lat": 23.0230, "lng": 72.5480, "property_types": ["Heritage residential flat", "Modern apartment"], "avg_rating": 4.81},
    "Ellis Bridge": {"base_listings": 65, "base_adr": 3800.0, "adr_std": 520.0, "base_unavailability": 0.51, "lat": 23.0250, "lng": 72.5700, "property_types": ["City center flat", "Riverfront suite"], "avg_rating": 4.78},
    "Vasna": {"base_listings": 60, "base_adr": 3200.0, "adr_std": 400.0, "base_unavailability": 0.47, "lat": 22.9990, "lng": 72.5490, "property_types": ["Entire apartment", "Family flat"], "avg_rating": 4.71},

    # North Ahmedabad
    "Chandkheda": {"base_listings": 95, "base_adr": 3100.0, "adr_std": 420.0, "base_unavailability": 0.46, "lat": 23.1150, "lng": 72.5850, "property_types": ["Suburban apartment", "Modern flat"], "avg_rating": 4.70},
    "Motera": {"base_listings": 110, "base_adr": 3900.0, "adr_std": 600.0, "base_unavailability": 0.52, "lat": 23.1020, "lng": 72.5970, "property_types": ["Stadium view apartment", "Modern condo"], "avg_rating": 4.81},
    "New Ranip": {"base_listings": 65, "base_adr": 2900.0, "adr_std": 380.0, "base_unavailability": 0.45, "lat": 23.0900, "lng": 72.5650, "property_types": ["Residential apartment", "Budget flat"], "avg_rating": 4.67},
    "Tragad": {"base_listings": 55, "base_adr": 3200.0, "adr_std": 430.0, "base_unavailability": 0.46, "lat": 23.1250, "lng": 72.5600, "property_types": ["Gated community flat", "Modern apartment"], "avg_rating": 4.72},
    "Chandlodia": {"base_listings": 60, "base_adr": 2800.0, "adr_std": 350.0, "base_unavailability": 0.44, "lat": 23.0780, "lng": 72.5420, "property_types": ["Residential flat", "Budget home"], "avg_rating": 4.66},

    # East Ahmedabad
    "Maninagar": {"base_listings": 85, "base_adr": 3300.0, "adr_std": 450.0, "base_unavailability": 0.49, "lat": 22.9980, "lng": 72.6030, "property_types": ["Kankaria lakeview flat", "Traditional apartment"], "avg_rating": 4.76},
    "Vastral": {"base_listings": 50, "base_adr": 2600.0, "adr_std": 320.0, "base_unavailability": 0.43, "lat": 23.0030, "lng": 72.6580, "property_types": ["Budget apartment", "Metro corridor flat"], "avg_rating": 4.64},
    "Nikol": {"base_listings": 65, "base_adr": 2700.0, "adr_std": 340.0, "base_unavailability": 0.44, "lat": 23.0480, "lng": 72.6730, "property_types": ["Modern flat", "Residential apartment"], "avg_rating": 4.68},
    "Naroda": {"base_listings": 60, "base_adr": 2700.0, "adr_std": 350.0, "base_unavailability": 0.44, "lat": 23.0720, "lng": 72.6530, "property_types": ["Commercial corridor flat", "Entire apartment"], "avg_rating": 4.65},
    "Nava Naroda": {"base_listings": 45, "base_adr": 2600.0, "adr_std": 320.0, "base_unavailability": 0.42, "lat": 23.0820, "lng": 72.6680, "property_types": ["Residential flat", "Budget home"], "avg_rating": 4.63},
    "Odhav": {"base_listings": 40, "base_adr": 2500.0, "adr_std": 300.0, "base_unavailability": 0.41, "lat": 23.0250, "lng": 72.6600, "property_types": ["Transit stay flat", "Industrial hub apartment"], "avg_rating": 4.60},

    # South / South-East
    "Narol": {"base_listings": 45, "base_adr": 2600.0, "adr_std": 320.0, "base_unavailability": 0.42, "lat": 22.9720, "lng": 72.5920, "property_types": ["Highway transit apartment", "Budget flat"], "avg_rating": 4.62},
    "Isanpur": {"base_listings": 45, "base_adr": 2700.0, "adr_std": 340.0, "base_unavailability": 0.43, "lat": 22.9850, "lng": 72.6050, "property_types": ["Residential home", "Family flat"], "avg_rating": 4.64},
    "Vatva": {"base_listings": 40, "base_adr": 2500.0, "adr_std": 310.0, "base_unavailability": 0.40, "lat": 22.9560, "lng": 72.6280, "property_types": ["Budget studio", "Commercial stay flat"], "avg_rating": 4.59},
    "Hathijan": {"base_listings": 35, "base_adr": 2600.0, "adr_std": 320.0, "base_unavailability": 0.41, "lat": 22.9450, "lng": 72.6550, "property_types": ["Ring road stay flat", "Entire apartment"], "avg_rating": 4.61},
}


class SimulatedMarketProvider(AirbnbDataProvider):
    """
    High-fidelity, deterministic simulated market provider for Ahmedabad.
    Used for historical dataset creation, offline resilience, and testing.
    Uses cryptographically stable seeding so values are reproducible across runs.
    """

    def __init__(self, observation_date: Optional[str] = None):
        self.observation_date = observation_date or datetime.now().strftime("%Y-%m-%d")

    def get_provider_name(self) -> str:
        return "SIMULATED_AHMEDABAD_ENGINE"

    def _get_seed(self, *parts: str) -> int:
        s = "_".join(parts)
        h = hashlib.md5(s.encode("utf-8")).hexdigest()
        return int(h[:8], 16)

    def search_listings(self, area: str, page: int = 1, page_size: int = 20) -> List[RawListing]:
        profile = AREA_PROFILES.get(area)
        if not profile:
            profile = {
                "base_listings": 50,
                "base_adr": 3000.0,
                "adr_std": 400.0,
                "base_unavailability": 0.45,
                "lat": 23.0225,
                "lng": 72.5714,
                "property_types": ["Apartment"],
                "avg_rating": 4.70,
            }

        total_listings = profile["base_listings"]
        # Allow slight growth/variation over dates
        obs_dt = datetime.strptime(self.observation_date, "%Y-%m-%d")
        days_from_epoch = (obs_dt - datetime(2026, 1, 1)).days
        
        # Slight organic growth in active listings
        growth_factor = 1.0 + (days_from_epoch * 0.0005)
        active_count = int(total_listings * growth_factor)

        listings: List[RawListing] = []
        for i in range(1, active_count + 1):
            seed = self._get_seed(area, str(i))
            rng = random.Random(seed)

            # Unique stable 18-digit listing ID
            listing_id = f"19{seed % 10000000000000000:016d}"
            
            # Stable listing characteristics adhering to global filters (2+ bedrooms, 2+ beds, wifi, AC)
            p_type = rng.choice(profile["property_types"])
            bedrooms = rng.choices([2, 3, 4], weights=[0.60, 0.32, 0.08])[0]
            beds = max(2, bedrooms + rng.choice([0, 1, 2]))
            bathrooms = float(max(1, bedrooms - (1 if rng.random() > 0.6 else 0)))
            rating = round(rng.uniform(profile["avg_rating"] - 0.25, min(5.0, profile["avg_rating"] + 0.15)), 2)
            review_count = rng.randint(8, 220)
            
            # Coordinates jitter within ~1-2km of area center
            lat_jitter = rng.uniform(-0.015, 0.015)
            lng_jitter = rng.uniform(-0.015, 0.015)
            lat = round(profile["lat"] + lat_jitter, 6)
            lng = round(profile["lng"] + lng_jitter, 6)
            
            # Base price for 2+ BHK AC properties
            base_p = profile["base_adr"] + (bedrooms - 2) * 850.0 + rng.gauss(0, profile["adr_std"] * 0.5)
            base_p = max(2200.0, round(base_p, -1))

            title = f"{bedrooms} BHK {p_type} in {area}, Ahmedabad"

            listings.append(
                RawListing(
                    listing_id=listing_id,
                    title=title,
                    area=area,
                    latitude=lat,
                    longitude=lng,
                    property_type=p_type,
                    room_type="Entire home/apt" if "room" not in p_type.lower() else "Private room",
                    bedrooms=bedrooms,
                    beds=beds,
                    bathrooms=bathrooms,
                    has_wifi=True,
                    has_ac=True,
                    rating=rating,
                    review_count=review_count,
                    nightly_price=base_p,
                    listing_url=f"https://www.airbnb.com/rooms/{listing_id}",
                    source="SIMULATED_OBSERVED",
                )
            )

        start_idx = (page - 1) * page_size
        return listings[start_idx : start_idx + page_size] if page_size > 0 else listings

    def get_all_active_listings(self, area: str) -> List[RawListing]:
        """Returns all listings for an area without pagination."""
        return self.search_listings(area, page=1, page_size=-1)

    def get_calendar(self, listing_id: str, horizon_days: int = 30) -> List[RawCalendarDay]:
        """
        Generate 30-day future calendar availability from observation_date.
        """
        obs_dt = datetime.strptime(self.observation_date, "%Y-%m-%d")
        
        # Determine listing base characteristics from ID
        base_seed = self._get_seed(listing_id)
        rng_base = random.Random(base_seed)
        
        # Listing's intrinsic base price and popularity
        intrinsic_price = rng_base.uniform(2200, 4800)
        popularity = rng_base.uniform(0.35, 0.70)  # Unavailability propensity
        min_stay = rng_base.choices([1, 2, 3], weights=[0.55, 0.35, 0.10])[0]

        calendar_days: List[RawCalendarDay] = []
        for d in range(horizon_days):
            cal_dt = obs_dt + timedelta(days=d)
            cal_date_str = cal_dt.strftime("%Y-%m-%d")
            
            # Seed combining listing + calendar date
            day_seed = self._get_seed(listing_id, cal_date_str)
            day_rng = random.Random(day_seed)
            
            is_weekend = cal_dt.weekday() in (4, 5)  # Friday, Saturday nights
            weekend_multiplier = 1.18 if is_weekend else 1.0
            
            # Near-term dates have higher booked/unavailable chance
            lead_time_days = d
            lead_time_factor = max(0.5, 1.3 - (lead_time_days * 0.025))
            
            p_unavailable = min(0.92, popularity * lead_time_factor * (1.2 if is_weekend else 1.0))
            is_unavailable = day_rng.random() < p_unavailable

            # Dynamic price
            day_price = round((intrinsic_price * weekend_multiplier) + day_rng.gauss(0, 150), -1)
            day_price = max(1800.0, day_price)

            if is_unavailable:
                # Sub-classify: booked vs blocked
                # 75% of unavailabilities are bookings, 25% host blocks/min-stay restrictions
                is_booked = day_rng.random() < 0.75
                status = "booked" if is_booked else "blocked"
                bookable = False
                raw_status = "RESERVED" if is_booked else "BLOCKED_BY_HOST"
            else:
                status = "available"
                bookable = True
                raw_status = "AVAILABLE"

            calendar_days.append(
                RawCalendarDay(
                    listing_id=listing_id,
                    calendar_date=cal_date_str,
                    status=status,
                    bookable=bookable,
                    price=day_price,
                    minimum_stay=min_stay,
                    raw_status=raw_status,
                    source="SIMULATED_OBSERVED",
                )
            )

        return calendar_days

    def get_listing_details(self, listing_id: str) -> Optional[RawListing]:
        # Fast lookup
        seed = self._get_seed(listing_id)
        rng = random.Random(seed)
        area = rng.choice(list(AREA_PROFILES.keys()))
        return RawListing(
            listing_id=listing_id,
            title=f"Apartment in {area}, Ahmedabad",
            area=area,
            listing_url=f"https://www.airbnb.com/rooms/{listing_id}",
            source="SIMULATED_OBSERVED",
        )
