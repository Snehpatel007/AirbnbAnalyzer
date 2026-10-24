import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.database import Base, Listing, CalendarObservation, DailyMarketMetric, CollectionRun
from src.pipeline.collector import normalize_slot
from src.pipeline.aggregator import DailyAggregator
from src.web.app import app, resolve_slot_for_date
from fastapi.testclient import TestClient


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    yield session
    session.close()


def test_slot_normalization():
    assert normalize_slot("4pm") == "4pm"
    assert normalize_slot("16:00") == "4pm"
    assert normalize_slot("4:00pm") == "4pm"
    assert normalize_slot("8pm") == "8pm"
    assert normalize_slot("20:00") == "8pm"
    assert normalize_slot("11.30pm") == "11.30pm"
    assert normalize_slot("11:30pm") == "11.30pm"
    assert normalize_slot("23:30") == "11.30pm"
    assert normalize_slot("manual") == "manual"
    assert normalize_slot("unknown") == "manual"
    assert normalize_slot(None) == "manual"


def test_intraday_slot_isolation_and_override_rules(in_memory_db):
    session = in_memory_db

    # 1. Past day data (2026-10-23)
    past_metric = DailyMarketMetric(
        observation_date="2026-10-23",
        snapshot_slot="4pm",
        area="Ahmedabad",
        active_listings=250,
        observed_unavailability_rate=0.70,
        adr=3200.0,
        revpar_proxy=2240.0,
        coverage_rate=1.0,
        status="COMPLETE",
    )
    session.add(past_metric)
    session.commit()

    # 2. Today (2026-10-24) 4:00 PM slot ingestion
    metric_4pm = DailyMarketMetric(
        observation_date="2026-10-24",
        snapshot_slot="4pm",
        area="Ahmedabad",
        active_listings=280,
        observed_unavailability_rate=0.72,
        adr=3400.0,
        revpar_proxy=2448.0,
        coverage_rate=1.0,
        status="COMPLETE",
    )
    session.add(metric_4pm)
    session.commit()

    # 3. Today (2026-10-24) First manual ingestion at 4:45 PM
    metric_manual_1 = DailyMarketMetric(
        observation_date="2026-10-24",
        snapshot_slot="manual",
        area="Ahmedabad",
        active_listings=282,
        observed_unavailability_rate=0.73,
        adr=3450.0,
        revpar_proxy=2518.5,
        coverage_rate=1.0,
        status="COMPLETE",
    )
    session.add(metric_manual_1)
    session.commit()

    # Verify both 4pm and manual exist for today
    today_metrics = session.query(DailyMarketMetric).filter(DailyMarketMetric.observation_date == "2026-10-24").all()
    assert len(today_metrics) == 2
    slots = {m.snapshot_slot for m in today_metrics}
    assert slots == {"4pm", "manual"}

    # 4. Today (2026-10-24) Second manual ingestion at 5:40 PM -> overrides previous manual of same day
    existing_manual = (
        session.query(DailyMarketMetric)
        .filter(
            DailyMarketMetric.observation_date == "2026-10-24",
            DailyMarketMetric.snapshot_slot == "manual",
            DailyMarketMetric.area == "Ahmedabad",
        )
        .first()
    )
    assert existing_manual is not None
    existing_manual.active_listings = 285
    existing_manual.adr = 3500.0
    session.commit()

    # Verify maximum 1 manual, 1 4pm for today; past day untouched
    all_metrics = session.query(DailyMarketMetric).all()
    assert len(all_metrics) == 3  # 1 past (4pm) + 1 today 4pm + 1 today manual

    past_in_db = session.query(DailyMarketMetric).filter(DailyMarketMetric.observation_date == "2026-10-23").first()
    assert past_in_db is not None
    assert past_in_db.active_listings == 250
    assert past_in_db.snapshot_slot == "4pm"

    today_manual = (
        session.query(DailyMarketMetric)
        .filter(DailyMarketMetric.observation_date == "2026-10-24", DailyMarketMetric.snapshot_slot == "manual")
        .first()
    )
    assert today_manual.active_listings == 285
    assert today_manual.adr == 3500.0


def test_calendar_observation_slot_isolation(in_memory_db):
    session = in_memory_db

    obs_4pm = CalendarObservation(
        listing_id="listing_1",
        calendar_date="2026-10-24",
        observation_date="2026-10-24",
        snapshot_slot="4pm",
        status="available",
        price=3000.0,
    )
    obs_manual = CalendarObservation(
        listing_id="listing_1",
        calendar_date="2026-10-24",
        observation_date="2026-10-24",
        snapshot_slot="manual",
        status="unavailable",
        price=3200.0,
    )
    session.add_all([obs_4pm, obs_manual])
    session.commit()

    rows_4pm = session.query(CalendarObservation).filter(
        CalendarObservation.observation_date == "2026-10-24",
        CalendarObservation.snapshot_slot == "4pm"
    ).all()
    assert len(rows_4pm) == 1
    assert rows_4pm[0].status == "available"

    rows_manual = session.query(CalendarObservation).filter(
        CalendarObservation.observation_date == "2026-10-24",
        CalendarObservation.snapshot_slot == "manual"
    ).all()
    assert len(rows_manual) == 1
    assert rows_manual[0].status == "unavailable"


def test_api_slot_filtering_and_available_slots(in_memory_db):
    client = TestClient(app)
    
    # Check that resolve_slot_for_date defaults to manual when empty
    resolved = resolve_slot_for_date(in_memory_db, "2026-10-24", "4pm")
    assert resolved == "4pm"
    resolved_latest = resolve_slot_for_date(in_memory_db, "2026-10-24", "latest")
    assert resolved_latest == "manual"
