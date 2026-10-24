import pytest
from config.settings import load_market_config, settings
from src.models.database import Listing, CalendarObservation, DailyMarketMetric, CollectionRun, Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_areas_configuration():
    cfg = load_market_config()
    assert cfg.city == "Ahmedabad"
    assert cfg.country == "India"
    assert cfg.timezone == "Asia/Kolkata"
    assert cfg.collection_time_ist in ("17:00", "01:00", "00:50", "09:00")
    assert cfg.calendar_horizon_days == 7
    
    # Discovered dynamic unique areas from Ahmedabad city range
    assert len(cfg.areas) >= 20
    for key_area in ["Navrangpura", "Tragad", "Motera", "Shela", "Ambli", "Thaltej", "Bodakdev"]:
        assert key_area in cfg.areas, f"Missing key discovered area: {key_area}"

    assert cfg.global_filters.min_bedrooms == 2
    assert cfg.global_filters.min_beds == 2
    assert cfg.global_filters.requires_wifi is True
    assert cfg.global_filters.requires_air_conditioning is True


def test_database_models_in_memory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    listing = Listing(
        listing_id="1234567890",
        title="Apartment in Bopal, Ahmedabad",
        area="Bopal",
        latitude=23.033,
        longitude=72.463,
        property_type="Apartment",
        room_type="Entire home/apt",
        bedrooms=2,
        bathrooms=2.0,
        rating=4.85,
        review_count=42,
        is_active=True,
    )
    session.add(listing)
    session.commit()

    saved = session.query(Listing).filter_by(listing_id="1234567890").first()
    assert saved is not None
    assert saved.area == "Bopal"
    assert saved.bedrooms == 2
    assert saved.to_dict()["listing_id"] == "1234567890"

    obs = CalendarObservation(
        listing_id="1234567890",
        observation_date="2026-10-04",
        calendar_date="2026-10-15",
        status="available",
        bookable=True,
        price=3200.0,
        minimum_stay=2,
        raw_status="AVAILABLE",
    )
    session.add(obs)
    session.commit()

    saved_obs = session.query(CalendarObservation).filter_by(listing_id="1234567890").first()
    assert saved_obs is not None
    assert saved_obs.price == 3200.0
    assert saved_obs.bookable is True
    session.close()


def test_session_manager_parse_curl(tmp_path):
    from src.providers.session_manager import AirbnbSessionManager
    test_session_file = tmp_path / "airbnb_session.json"
    mgr = AirbnbSessionManager(session_path=test_session_file)

    sample_curl = """
    curl --url 'https://www.airbnb.co.in/api/v3/StaysSearch/2aa7c66c6c086fabcadbfb48a19f6c742e07f4eaa3b430a2e4090d22585096cd?operationName=StaysSearch' \
      -H 'x-airbnb-api-key: d306zoyjsyarp7ifhu67rjxn52tv0t20' \
      -b 'bev=1791124028_EAZj; datadome=test_token_value; sticky_locale=en' \
      -H 'accept: */*'
    """
    res = mgr.update_from_curl(sample_curl)
    assert res["api_key"] == "d306zoyjsyarp7ifhu67rjxn52tv0t20"
    assert res["query_hash"] == "2aa7c66c6c086fabcadbfb48a19f6c742e07f4eaa3b430a2e4090d22585096cd"
    assert res["cookies"]["bev"] == "1791124028_EAZj"
    assert res["cookies"]["datadome"] == "test_token_value"
    assert test_session_file.exists()

