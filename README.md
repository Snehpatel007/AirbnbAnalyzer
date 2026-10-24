# Ahmedabad Airbnb Daily Market Tracker

A production-ready system that tracks the Ahmedabad Airbnb market on a daily basis for evaluating an Airbnb business operated on a lease model.

---

## 1. Core Principles

1. **Observed Data as Ground Truth**: The system maintains its own historical dataset calculated directly from observed Airbnb listings and calendar availability.
2. **No Third-Party Estimates**: Does **NOT** rely on AirDNA, AirROI, or estimated blackbox numbers.
3. **Strict Terminology**:
   - **Observed Unavailability Rate** (`unavailable_nights / total_calendar_nights`) is the primary metric.
   - If the provider explicitly distinguishes booked vs blocked, `Confirmed Booking Occupancy` and `Blocked Rate` are separated.
   - Otherwise, the rate is labeled as an **Observed Proxy**.
4. **Observed RevPAR Proxy**:
   $$\text{Observed RevPAR Proxy} = \text{ADR} \times \text{Observed Unavailability Rate}$$
5. **Coverage Metric**:
   $$\text{Coverage} = \frac{\text{Successfully observed active listings}}{\text{Expected active listings}}$$
   Every run publishes its coverage rate. If coverage $< 95\%$, the run is flagged as `PARTIAL`.
6. **No Overwrites**: Historical observations are immutable day-by-day snapshots.

---

## 2. Tracked Ahmedabad Areas

Configured in [`config/areas.json`](file:///Users/snehpatel/Desktop/AIrbnbAnalyzer/config/areas.json) without hardcoding:
* **Bopal**
* **Ghuma**
* **Shilaj**
* **Shela**
* **South Bopal**
* **Thaltej**
* **SG Highway**
* **Prahlad Nagar**

---

## 3. Architecture & Data Flow

```text
Airbnb Listings (Discovery)
         ↓
Airbnb Calendar Observations (30-Day Forward Horizon)
         ↓
Master Database (listings, calendar_observations)
         ↓
Deterministic Aggregator (City & Area Daily Metrics)
         ↓
Daily 9:00 AM IST Scheduler & Reports
         ↓
Interactive Glassmorphism Dashboard & Historical Trends
         ↓
Fact-Grounded AI Market Analyst Agent
```

---

## 4. Database Schema (SQLite / SQLAlchemy)

The database is stored in `data/airbnbanalyzer.db`.

* **`listings`**: Master universe with stable `listing_id`, coordinates, property type, room type, rating, review count, `first_seen_at`, `last_seen_at`, `is_active`.
* **`calendar_observations`**: One record per `listing_id + calendar_date + observation_date`, storing status (`available`, `booked`, `blocked`, `unavailable`), bookable boolean, nightly price, minimum stay, and raw status.
* **`daily_market_metrics`**: Daily aggregated snapshot for Ahmedabad overall and each area: active listings, available/unavailable nights, unavailability rate, booking occupancy (if confirmed), ADR, RevPAR proxy, 1D/7D/30D changes, coverage rate, status (`COMPLETE` or `PARTIAL`).
* **`collection_runs`**: Audit log of all runs: run ID, start/end timestamps, listings discovered, calendar records collected, coverage %, errors, and provider.

---

## 5. Daily 9:00 AM IST Scheduler

Configured with `APScheduler` for `09:00 Asia/Kolkata` (`CronTrigger(hour=9, minute=0, timezone="Asia/Kolkata")`).

---

## 6. CLI Commands

```bash
# Start the web dashboard and scheduler
python3 main.py run-server --host 127.0.0.1 --port 8000

# Run on-demand daily collection
python3 main.py run-collection --date 2026-10-04

# Generate 9 AM daily market intelligence report
python3 main.py generate-report --date 2026-10-04

# Seed 30-day historical observations for testing & trend verification
python3 main.py seed-history --days 30 --end-date 2026-10-04
```

---

## 7. Natural Language AI Analysis Agent

The system provides a fact-grounded analysis agent answering queries such as:
* *"Compare Bopal vs Shilaj"*
* *"Which area has the highest ADR?"*
* *"Which areas currently have the best combination of observed occupancy, ADR and RevPAR?"*
* *"Which area has improved the most in the last 30 days?"*
* *"Which area has increasing demand but decreasing supply?"*
* *"Show me Ghuma's last 30 days."*

All answers are derived deterministically from historical database metrics.

---

## 8. Running Automated Tests

```bash
pytest -v
```
All unit tests validate data quality rules, metric calculation formulas, database persistence, and AI analyst reasoning.
