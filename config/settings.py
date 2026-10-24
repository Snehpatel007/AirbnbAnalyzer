import json
import os
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "areas.json"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class GlobalFiltersConfig(BaseModel):
    min_bedrooms: int = 2
    min_beds: int = 2
    requires_wifi: bool = True
    requires_air_conditioning: bool = True


class MapBoundsConfig(BaseModel):
    sw_lat: float = 22.88872571278057
    sw_lng: float = 72.41636370491506
    ne_lat: float = 23.298188302253283
    ne_lng: float = 72.72146434828014


class MarketConfig(BaseModel):
    city: str = "Ahmedabad & Gandhinagar"
    country: str = "India"
    timezone: str = "Asia/Kolkata"
    collection_time_ist: str = os.getenv("COLLECTION_TIME_IST", "17:00")
    calendar_horizon_days: int = 7
    inactivity_days_threshold: int = 3
    default_currency: str = "INR"
    global_filters: GlobalFiltersConfig = Field(default_factory=GlobalFiltersConfig)
    map_bounds: MapBoundsConfig = Field(default_factory=MapBoundsConfig)
    areas: List[str] = Field(default_factory=list)


def load_market_config() -> MarketConfig:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return MarketConfig(**data)
    return MarketConfig(
        areas=[
            "GIFT City", "Kudasan", "Raysan", "Sargasan", "Infocity", "Gandhinagar",
            "SG Highway", "Thaltej", "Bodakdev", "Satellite", "Prahlad Nagar",
            "Vastrapur", "Sola", "Science City", "Sindhu Bhavan Road", "Shilaj", "Gota",
            "Bopal", "South Bopal", "Ghuma", "Shela", "Ambli", "Makarba", "Jodhpur", "Sarkhej",
            "Navrangpura", "CG Road", "Paldi", "Ambawadi", "Ellis Bridge", "Vasna",
            "Chandkheda", "Motera", "New Ranip", "Tragad", "Chandlodia",
            "Maninagar", "Vastral", "Nikol", "Naroda", "Nava Naroda", "Odhav",
            "Narol", "Isanpur", "Vatva", "Hathijan"
        ]
    )


class Settings(BaseModel):
    app_name: str = "Ahmedabad & Gandhinagar Airbnb Daily Market Tracker"
    db_path: Path = DATA_DIR / "airbnbanalyzer.db"
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'airbnbanalyzer.db'}")
    market_config: MarketConfig = Field(default_factory=load_market_config)
    
    # Provider Settings: "direct_web", "hybrid", "rapidapi", "apify", "simulation"
    data_provider: str = os.getenv("DATA_PROVIDER", "direct_web")
    rapidapi_key: str = os.getenv("RAPIDAPI_KEY", "")
    rapidapi_host: str = os.getenv("RAPIDAPI_HOST", "airbnb13.p.rapidapi.com")
    apify_token: str = os.getenv("APIFY_TOKEN", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    
    # Airbnb Native / Web Client Configuration
    airbnb_api_key: str = os.getenv("AIRBNB_API_KEY", "d306zoyjsyarp7ifhu67rjxn52tv0t20")
    airbnb_bearer_token: Optional[str] = os.getenv("AIRBNB_BEARER_TOKEN", None)
    
    # Rate Limit & API Optimization: False avoids ~275 individual calendar calls
    fetch_individual_calendars: bool = os.getenv("FETCH_INDIVIDUAL_CALENDARS", "false").lower() in ("true", "1", "yes")

    # Scheduler
    scheduler_enabled: bool = os.getenv("SCHEDULER_ENABLED", "true").lower() in ("true", "1", "yes")
    
    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))


settings = Settings()
