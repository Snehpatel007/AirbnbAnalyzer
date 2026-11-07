import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from src.models.database import Base, Listing, CalendarObservation, DailyMarketMetric, get_db
from src.web.app import app


@pytest.fixture
def test_db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_stay_criteria_filtering(test_db_session):
    db = test_db_session
    obs_date = "2026-11-06"
    slot = "manual"

    # Seed 3 listings in Tragad:
    # 1. No criteria (min_nights=1)
    l1 = Listing(
        listing_id="listing_1",
        title="Tragad 1-Night Apt",
        area="Tragad",
        is_active=True,
        min_nights=1,
    )
    # 2. 2-day criteria (min_nights=2)
    l2 = Listing(
        listing_id="listing_2",
        title="Tragad 2-Night Apt",
        area="Tragad",
        is_active=True,
        min_nights=2,
    )
    # 3. 3-day criteria (min_nights=3)
    l3 = Listing(
        listing_id="listing_3",
        title="Tragad 3-Night Apt",
        area="Tragad",
        is_active=True,
        min_nights=3,
    )
    db.add_all([l1, l2, l3])

    # Add calendar observations
    for l in [l1, l2, l3]:
        for i in range(3):
            cal_dt = (datetime.strptime(obs_date, "%Y-%m-%d") + timedelta(days=i)).strftime("%Y-%m-%d")
            db.add(CalendarObservation(
                listing_id=l.listing_id,
                observation_date=obs_date,
                calendar_date=cal_dt,
                status="available" if l.listing_id == "listing_1" else "unavailable",
                minimum_stay=l.min_nights,
                snapshot_slot=slot
            ))

    # Add baseline DailyMarketMetric
    db.add(DailyMarketMetric(
        observation_date=obs_date,
        snapshot_slot=slot,
        area="Tragad",
        active_listings=3,
        observed_unavailability_rate=0.6667,
        adr=3200.0,
        revpar_proxy=2133.0,
        unavailability_1d=0.6667,
        unavailability_2d=0.6667,
        unavailability_3d=0.6667,
    ))
    db.commit()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        # 1. Overview with criteria=all -> returns all 3 listings
        res_all = client.get(f"/api/overview?area=Tragad&date={obs_date}&slot={slot}&criteria=all")
        assert res_all.status_code == 200
        assert res_all.json()["metric"]["active_listings"] == 3

        # 2. Overview with criteria=1 -> returns only 1 listing (listing_1)
        res_1 = client.get(f"/api/overview?area=Tragad&date={obs_date}&slot={slot}&criteria=1")
        assert res_1.status_code == 200
        assert res_1.json()["metric"]["active_listings"] == 1
        assert res_1.json()["metric"]["unavailability_1d"] == 0.0

        # 3. Overview with criteria=3 -> returns only 1 listing (listing_3)
        res_3 = client.get(f"/api/overview?area=Tragad&date={obs_date}&slot={slot}&criteria=3")
        assert res_3.status_code == 200
        assert res_3.json()["metric"]["active_listings"] == 1
        assert res_3.json()["metric"]["unavailability_1d"] == 1.0

        # 4. Listings endpoint with criteria=3
        res_list = client.get(f"/api/listings?area=Tragad&criteria=3")
        assert res_list.status_code == 200
        listings = res_list.json()["listings"]
        assert len(listings) == 1
        assert listings[0]["listing_id"] == "listing_3"
        assert listings[0]["min_nights"] == 3

        # 5. Area comparison with criteria=2
        res_comp = client.get(f"/api/comparison?date={obs_date}&slot={slot}&criteria=2")
        assert res_comp.status_code == 200
        areas = res_comp.json()["areas"]
        assert len(areas) == 1
        assert areas[0]["area"] == "Tragad"
        assert areas[0]["active_listings"] == 1

        # 6. Trends endpoint with criteria=3
        res_trends = client.get(f"/api/trends?area=Tragad&criteria=3")
        assert res_trends.status_code == 200
        t_data = res_trends.json()["data"]
        assert len(t_data) == 1
        assert t_data[0]["active_listings"] == 1
        assert t_data[0]["unavailability_1d"] == 1.0

    finally:
        app.dependency_overrides.clear()
