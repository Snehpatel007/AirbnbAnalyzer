import pytest
from src.models.schema import RawListing, RawCalendarDay
from src.pipeline.validator import DataQualityValidator
from src.pipeline.aggregator import DailyAggregator
from src.models.database import Base, Listing, CalendarObservation, DailyMarketMetric
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_global_listing_filters():
    raw = [
        RawListing(listing_id="201", title="2 BHK Flat", area="Bopal", bedrooms=2, beds=2, has_wifi=True, has_ac=True),
        RawListing(listing_id="202", title="1 BHK Flat", area="Bopal", bedrooms=1, beds=2, has_wifi=True, has_ac=True), # 1 bedroom
        RawListing(listing_id="203", title="2 BHK Flat (1 bed)", area="Bopal", bedrooms=2, beds=1, has_wifi=True, has_ac=True), # 1 bed
        RawListing(listing_id="204", title="2 BHK No Wifi", area="Bopal", bedrooms=2, beds=2, has_wifi=False, has_ac=True), # No wifi
        RawListing(listing_id="205", title="2 BHK No AC", area="Bopal", bedrooms=2, beds=2, has_wifi=True, has_ac=False), # No AC
    ]
    valid, errors = DataQualityValidator.validate_listings(raw)
    assert len(valid) == 1
    assert valid[0].listing_id == "201"
    assert len(errors) == 4
    assert any("min_bedrooms" in e for e in errors)
    assert any("min_beds" in e for e in errors)
    assert any("WiFi" in e for e in errors)
    assert any("Air Conditioning" in e for e in errors)


def test_data_quality_validator_calendar():
    days = [
        RawCalendarDay(listing_id="101", calendar_date="2026-10-05", status="available", bookable=True, price=3000.0),
        RawCalendarDay(listing_id="101", calendar_date="2026-10-01", status="available"), # Past date compared to 2026-10-04
        RawCalendarDay(listing_id="101", calendar_date="invalid-date", status="available"),
        RawCalendarDay(listing_id="", calendar_date="2026-10-06", status="available"),
    ]
    valid, errors = DataQualityValidator.validate_calendar_days(days, observation_date="2026-10-04")
    assert len(valid) == 1
    assert valid[0].calendar_date == "2026-10-05"
    assert len(errors) == 3


def test_metric_calculations_unavailability_and_revpar():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Add 2 listings in Bopal
    l1 = Listing(listing_id="L1", title="L1", area="Bopal", is_active=True)
    l2 = Listing(listing_id="L2", title="L2", area="Bopal", is_active=True)
    session.add_all([l1, l2])
    session.commit()

    # Add 10 calendar days for L1 (5 available, 5 unavailable)
    for i in range(1, 11):
        status = "available" if i <= 5 else "booked"
        price = 3000.0 if status == "available" else 3200.0
        c = CalendarObservation(
            listing_id="L1",
            observation_date="2026-10-04",
            calendar_date=f"2026-10-{i:02d}",
            status=status,
            bookable=(status == "available"),
            price=price,
        )
        session.add(c)

    # Add 10 calendar days for L2 (2 available, 8 blocked)
    for i in range(1, 11):
        status = "available" if i <= 2 else "blocked"
        c = CalendarObservation(
            listing_id="L2",
            observation_date="2026-10-04",
            calendar_date=f"2026-10-{i:02d}",
            status=status,
            bookable=(status == "available"),
            price=4000.0,
        )
        session.add(c)
    session.commit()

    aggregator = DailyAggregator(session, observation_date="2026-10-04")
    metric = aggregator.calculate_for_area("Bopal", expected_listings=2, observed_listings=2)

    # Tonight's observation (2026-10-04 only):
    # Total listings observed = 2
    # L1 on 2026-10-04 is available (price 3000)
    # L2 on 2026-10-04 is blocked/unavailable (price 4000)
    # Unavailable = 1, Available = 1
    # Observed Unavailability Rate = 1 / 2 = 0.50 (50.0%)
    assert metric.observed_unavailability_rate == 0.50
    assert metric.unavailable_listing_nights == 1
    assert metric.available_listing_nights == 1

    # ADR: (3000 + 4000) / 2 = 3500.0
    assert metric.adr == 3500.0

    # RevPAR Proxy = ADR * Observed Unavailability Rate = 3500.0 * 0.50 = 1750.0
    assert metric.revpar_proxy == 1750.0

    # Coverage
    assert metric.coverage_rate == 1.0
    assert metric.status == "COMPLETE"

    session.close()


def test_city_overall_aggregation_excludes_non_configured_areas():
    from src.models.database import DailyMarketMetric
    from unittest.mock import MagicMock
    from src.pipeline.aggregator import DailyAggregator

    mock_db = MagicMock()
    aggregator = DailyAggregator(mock_db, observation_date="2026-10-04")

    # Configured area metrics
    m_navrangpura = DailyMarketMetric(
        observation_date="2026-10-04",
        area="Navrangpura",
        active_listings=100,
        available_listing_nights=1500,
        unavailable_listing_nights=1500,
        observed_unavailability_rate=0.50,
        adr=3500.0,
        revpar_proxy=1750.0,
        coverage_rate=1.0,
    )
    m_thaltej = DailyMarketMetric(
        observation_date="2026-10-04",
        area="Thaltej",
        active_listings=100,
        available_listing_nights=1000,
        unavailable_listing_nights=2000,
        observed_unavailability_rate=0.6667,
        adr=4000.0,
        revpar_proxy=2666.8,
        coverage_rate=1.0,
    )
    # Outside/Non-configured area metric (should be ignored)
    m_outside = DailyMarketMetric(
        observation_date="2026-10-04",
        area="Vadodara",
        active_listings=500,
        available_listing_nights=5000,
        unavailable_listing_nights=10000,
        observed_unavailability_rate=0.90,
        adr=9999.0,
        revpar_proxy=8999.1,
        coverage_rate=1.0,
    )

    area_metrics = [m_navrangpura, m_thaltej, m_outside]
    city_metric = aggregator.calculate_city_overall(area_metrics, expected_total=200, observed_total=200)

    # Must only aggregate Navrangpura + Thaltej (200 listings), ignoring Vadodara
    assert city_metric.area == "Ahmedabad"
    assert city_metric.active_listings == 200
    assert city_metric.available_listing_nights == 2500
    assert city_metric.unavailable_listing_nights == 3500
    assert city_metric.observed_unavailability_rate == round(3500 / 6000, 4)
    # Weighted ADR: (100 * 3500 + 100 * 4000) / 200 = 3750.0
    assert city_metric.adr == 3750.0
    assert city_metric.status == "COMPLETE"


def test_multi_horizon_matrix_calculations():
    """Verify user's exact specification:
    In Sola there are 3 properties:
    1. 3/7 days occupied
    2. 1/7 days occupied
    3. 6/7 days occupied
    Occupancy rate for 7 days in Sola = 10/21 = 0.4762
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from src.models.database import Base, Listing, CalendarObservation
    from src.pipeline.aggregator import DailyAggregator
    from datetime import datetime, timedelta

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    obs_date = "2026-10-04"
    obs_dt = datetime.strptime(obs_date, "%Y-%m-%d")

    # 3 active properties in Sola
    l1 = Listing(listing_id="sola_1", area="Sola", is_active=True, bedrooms=2, beds=2, has_wifi=True, has_ac=True)
    l2 = Listing(listing_id="sola_2", area="Sola", is_active=True, bedrooms=2, beds=2, has_wifi=True, has_ac=True)
    l3 = Listing(listing_id="sola_3", area="Sola", is_active=True, bedrooms=2, beds=2, has_wifi=True, has_ac=True)
    db.add_all([l1, l2, l3])
    db.commit()

    # Schedule:
    # l1: occupied on days 0, 1, 2 (3/7)
    # l2: occupied on day 0 (1/7)
    # l3: occupied on days 0, 1, 2, 3, 4, 5 (6/7)
    cal_rows = []
    for day_idx in range(7):
        cal_dt = (obs_dt + timedelta(days=day_idx)).strftime("%Y-%m-%d")
        
        # l1
        st1 = "unavailable" if day_idx in [0, 1, 2] else "available"
        cal_rows.append(CalendarObservation(listing_id="sola_1", observation_date=obs_date, calendar_date=cal_dt, status=st1, price=3000.0))
        
        # l2
        st2 = "unavailable" if day_idx == 0 else "available"
        cal_rows.append(CalendarObservation(listing_id="sola_2", observation_date=obs_date, calendar_date=cal_dt, status=st2, price=3000.0))
        
        # l3
        st3 = "unavailable" if day_idx in [0, 1, 2, 3, 4, 5] else "available"
        cal_rows.append(CalendarObservation(listing_id="sola_3", observation_date=obs_date, calendar_date=cal_dt, status=st3, price=3000.0))

    db.add_all(cal_rows)
    db.commit()

    aggregator = DailyAggregator(db, observation_date=obs_date)
    metric = aggregator.calculate_for_area("Sola", expected_listings=3, observed_listings=3)

    assert metric.active_listings == 3
    # 7D: Occupied = 3 + 1 + 6 = 10. Total = 3 * 7 = 21. Rate = 10 / 21
    assert metric.nights_unavail_7d == 10
    assert metric.nights_total_7d == 21
    assert metric.unavailability_7d == round(10 / 21, 4)

    # 1D: Tonight (day 0): all 3 properties occupied => 3/3 = 1.0
    assert metric.nights_unavail_1d == 3
    assert metric.nights_total_1d == 3
    assert metric.unavailability_1d == 1.0

    # 2D: Next 2 days (days 0, 1): l1 (2), l2 (1), l3 (2) => 5/6 = 0.8333
    assert metric.nights_unavail_2d == 5
    assert metric.nights_total_2d == 6
    assert metric.unavailability_2d == round(5 / 6, 4)

    # 3D: Next 3 days (days 0, 1, 2): l1 (3), l2 (1), l3 (3) => 7/9 = 0.7778
    assert metric.nights_unavail_3d == 7
    assert metric.nights_total_3d == 9
    assert metric.unavailability_3d == round(7 / 9, 4)


def test_geocoder_area_detection_and_boundary():
    from src.pipeline.geocoder import geocoder

    # Title match priority
    area, in_scope = geocoder.resolve_listing_area("101", "Spacious 2BHK in Bopal", 23.033, 72.468, "Unknown")
    assert area == "Bopal"
    assert in_scope is True

    # Coordinate match for Motera/Chandkheda
    area, in_scope = geocoder.resolve_listing_area("102", "Retreat Flat", 23.098, 72.595, "Unknown")
    assert area in ("Motera", "Chandkheda")
    assert in_scope is True

    # Far-flung property outside Ahmedabad (> 6 km from all centroids, e.g. Dholera or GIFT)
    area, in_scope = geocoder.resolve_listing_area("103", "Dholera Stay", 22.25, 72.20, "Unknown")
    assert area == "Outside Ahmedabad"
    assert in_scope is False



