import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.database import Base, CollectionRun
from src.providers.session_manager import AirbnbSessionManager
from src.pipeline.collector import MarketCollector, check_and_heal_audit_failures


def test_is_deprecation_error_detection():
    # True cases
    assert MarketCollector.is_deprecation_error("StaysSearch GraphQL API returned status 400")
    assert MarketCollector.is_deprecation_error("deprecated_web_operation")
    assert MarketCollector.is_deprecation_error("StaysSearch hash 2aa7c9f4... deprecated by Airbnb")
    assert MarketCollector.is_deprecation_error("PdpAvailabilityCalendar returned HTTP 400")
    assert MarketCollector.is_deprecation_error("StaysSearch hash deprecated by Airbnb. Auto-resolving live query hash...")
    assert MarketCollector.is_deprecation_error("Missing operationId in persistedQuery")

    # False cases
    assert not MarketCollector.is_deprecation_error("Rate limit HTTP 429")
    assert not MarketCollector.is_deprecation_error("Connection timeout")
    assert not MarketCollector.is_deprecation_error("Internal server error 500")


def test_session_manager_update_operation_hashes(tmp_path):
    sess_file = tmp_path / "airbnb_session.json"
    mgr = AirbnbSessionManager(session_path=sess_file)
    initial_data = {
        "api_key": "test_key",
        "stays_search_hash": "old_stays_hash_old_stays_hash_old_stays_hash_old_stays_hash_1234",
        "calendar_hash": "old_cal_hash_old_cal_hash_old_cal_hash_old_cal_hash_old_cal_5678",
        "calendar_operation": "PdpAvailabilityCalendar",
        "updated_at": "2026-11-14T00:00:00"
    }
    mgr.save_session(initial_data)

    new_stays = "aec09eb74dbd01c4019adbb6b4fcc3cc2ca224457ebcc3a2219bb4f4f5c8f206"
    new_cal = "f959cc8f218edf71f437ad301eaa2ad974c62c5fbac8cc4a04611813e30d3fbd"
    new_op = "PdpAvailabilityCalendarV2ExcludedQuery"

    updated = mgr.update_operation_hashes(stays_hash=new_stays, cal_hash=new_cal, cal_op=new_op)

    assert updated["stays_search_hash"] == new_stays
    assert updated["calendar_hash"] == new_cal
    assert updated["calendar_operation"] == new_op

    # Verify persisted to disk
    with open(sess_file, "r") as f:
        disk_data = json.load(f)
    assert disk_data["stays_search_hash"] == new_stays
    assert disk_data["calendar_hash"] == new_cal
    assert disk_data["calendar_operation"] == new_op


def test_check_and_heal_audit_failures():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # 1. Healthy database state -> returns HEALTHY
    healthy_run = CollectionRun(
        run_id="healthy-123",
        observation_date="2026-11-15",
        snapshot_slot="8pm",
        status="SUCCESS",
        coverage_pct=100.0,
        listings_discovered=280,
        calendar_records_collected=840,
        provider="DIRECT_AIRBNB_WEB",
        started_at=datetime.utcnow()
    )
    session.add(healthy_run)
    session.commit()

    res = check_and_heal_audit_failures(db=session, max_runs_to_check=5)
    assert res["status"] == "HEALTHY"
    assert res["healed_count"] == 0

    # 2. Add a failed run due to deprecated query hash
    failed_run = CollectionRun(
        run_id="failed-400",
        observation_date="2026-11-15",
        snapshot_slot="4pm",
        status="PARTIAL",
        coverage_pct=15.0,
        listings_discovered=42,
        calendar_records_collected=126,
        provider="DIRECT_AIRBNB_WEB",
        errors=json.dumps(["StaysSearch GraphQL API returned status 400", "deprecated_web_operation"]),
        started_at=datetime.utcnow()
    )
    session.add(failed_run)
    session.commit()

    # Mock dynamic hash extraction and collector run
    mock_hashes = {
        "stays_search_hash": "aec09eb74dbd01c4019adbb6b4fcc3cc2ca224457ebcc3a2219bb4f4f5c8f206",
        "calendar_hash": "f959cc8f218edf71f437ad301eaa2ad974c62c5fbac8cc4a04611813e30d3fbd",
    }
    mock_run_result = {
        "run_id": "healed-run-456",
        "observation_date": "2026-11-15",
        "snapshot_slot": "4pm",
        "status": "SUCCESS",
        "coverage_pct": 100.0,
        "listings_discovered": 280,
    }

    with patch("src.providers.direct_web.DirectWebAirbnbProvider.discover_and_update_all_hashes", return_value=mock_hashes), \
         patch.object(MarketCollector, "run", return_value=mock_run_result):

        heal_res = check_and_heal_audit_failures(db=session, max_runs_to_check=5)
        assert heal_res["status"] == "HEALED"
        assert heal_res["failed_runs_detected"] == 1
        assert heal_res["healed_count"] == 1
        assert heal_res["healed_runs"][0]["status"] == "SUCCESS"
        assert heal_res["refreshed_hashes"] == mock_hashes


def test_api_audit_auto_heal_endpoint():
    from src.web.app import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/audit/auto-heal")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["status"] in ("HEALTHY", "HEALED", "COMPLETED")


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    print("Running test_is_deprecation_error_detection...")
    test_is_deprecation_error_detection()
    print("  -> Passed")

    print("Running test_session_manager_update_operation_hashes...")
    with tempfile.TemporaryDirectory() as td:
        test_session_manager_update_operation_hashes(Path(td))
    print("  -> Passed")

    print("Running test_check_and_heal_audit_failures...")
    test_check_and_heal_audit_failures()
    print("  -> Passed")

    print("\nAll audit auto-heal unit tests passed successfully!")
