import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from src.models.schema import RawListing, RawCalendarDay
from src.providers.direct_web import DirectWebAirbnbProvider
from src.pipeline.aggregator import DailyAggregator
from src.models.database import Base, Listing, CalendarObservation
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_multi_length_date_search_captures_min_stay_listings():
    """
    Test that listings with minimum stay criteria (e.g. 3 nights)
    are captured as available / unoccupied when searching multi-night ranges.
    """
    provider = DirectWebAirbnbProvider(timeout_sec=5.0)

    # Mock search_by_map_bounds to simulate:
    # - listing_1: min_stay = 1 (appears in stay_len 1..7)
    # - listing_3: min_stay = 3 (appears only in stay_len 3..7)
    # - listing_occ: occupied (appears in NO search)
    def mock_search_by_map_bounds(checkin=None, checkout=None, max_pages=4):
        # Calculate stay length
        d_in = datetime.strptime(checkin, "%Y-%m-%d")
        d_out = datetime.strptime(checkout, "%Y-%m-%d")
        stay_len = (d_out - d_in).days

        results = []
        # listing_1 is available for any stay length >= 1
        results.append(RawListing(
            listing_id="listing_1",
            title="1-night stay apartment",
            area="Bodakdev",
            nightly_price=3000.0,
            bedrooms=2, beds=2, bathrooms=1.0, has_wifi=True, has_ac=True
        ))

        # listing_3 is available only if stay length >= 3
        if stay_len >= 3:
            results.append(RawListing(
                listing_id="listing_3",
                title="3-night min stay apartment",
                area="Bodakdev",
                nightly_price=3500.0,
                bedrooms=2, beds=2, bathrooms=1.0, has_wifi=True, has_ac=True
            ))

        return results

    provider.search_by_map_bounds = MagicMock(side_effect=mock_search_by_map_bounds)

    master_ids = ["listing_1", "listing_3", "listing_occ"]
    calendar_days = provider.get_horizon_calendar_by_date_search(
        master_listing_ids=master_ids,
        start_date="2026-11-06",
        horizon_days=3,
        listing_base_prices={"listing_occ": 4000.0}
    )

    # listing_1 should be available on all 3 days with min_stay 1
    assert len(calendar_days["listing_1"]) == 3
    for day in calendar_days["listing_1"]:
        assert day.status == "available"
        assert day.bookable is True
        assert day.minimum_stay == 1

    # listing_3 should ALSO be detected as available with min_stay 3
    assert len(calendar_days["listing_3"]) == 3
    for day in calendar_days["listing_3"]:
        assert day.status == "available"
        assert day.bookable is True
        assert day.minimum_stay == 3

    # listing_occ should be marked unavailable on all 3 days
    assert len(calendar_days["listing_occ"]) == 3
    for day in calendar_days["listing_occ"]:
        assert day.status == "unavailable"
        assert day.bookable is False


def test_3_day_horizon_aggregator():
    """
    Test aggregator calculations for 1D, 2D, and 3D horizons.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    obs_date = "2026-11-06"
    obs_dt = datetime.strptime(obs_date, "%Y-%m-%d")

    l1 = Listing(listing_id="l1", area="Bodakdev", is_active=True, bedrooms=2, beds=2, has_wifi=True, has_ac=True)
    l2 = Listing(listing_id="l2", area="Bodakdev", is_active=True, bedrooms=2, beds=2, has_wifi=True, has_ac=True)
    db.add_all([l1, l2])
    db.commit()

    # Day 0: l1 available, l2 unavailable (1/2 = 50% occupied)
    # Day 1: l1 available, l2 available (0/2 = 0% occupied)
    # Day 2: l1 unavailable, l2 unavailable (2/2 = 100% occupied)
    records = [
        # Day 0
        CalendarObservation(listing_id="l1", observation_date=obs_date, calendar_date="2026-11-06", status="available", price=3000.0),
        CalendarObservation(listing_id="l2", observation_date=obs_date, calendar_date="2026-11-06", status="unavailable", price=3000.0),
        # Day 1
        CalendarObservation(listing_id="l1", observation_date=obs_date, calendar_date="2026-11-07", status="available", price=3000.0),
        CalendarObservation(listing_id="l2", observation_date=obs_date, calendar_date="2026-11-07", status="available", price=3000.0),
        # Day 2
        CalendarObservation(listing_id="l1", observation_date=obs_date, calendar_date="2026-11-08", status="unavailable", price=3000.0),
        CalendarObservation(listing_id="l2", observation_date=obs_date, calendar_date="2026-11-08", status="unavailable", price=3000.0),
    ]
    db.add_all(records)
    db.commit()

    agg = DailyAggregator(db, observation_date=obs_date)
    m = agg.calculate_for_area("Bodakdev", expected_listings=2, observed_listings=2)

    # 1D: Day 0 -> 1/2 = 0.5
    assert m.nights_total_1d == 2
    assert m.nights_unavail_1d == 1
    assert m.unavailability_1d == 0.5

    # 2D: Day 0 + Day 1 -> 1 unavail out of 4 -> 0.25
    assert m.nights_total_2d == 4
    assert m.nights_unavail_2d == 1
    assert m.unavailability_2d == 0.25

    # 3D: Day 0 + Day 1 + Day 2 -> 1 + 0 + 2 = 3 unavail out of 6 -> 0.5
    assert m.nights_total_3d == 6
    assert m.nights_unavail_3d == 3
    assert m.unavailability_3d == 0.5

    # 7D: Discarded / 0
    assert m.nights_total_7d == 0
    assert m.unavailability_7d is None

