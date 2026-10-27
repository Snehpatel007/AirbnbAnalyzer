from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel
from fastapi import FastAPI, Depends, Query, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc

from config.settings import settings, load_market_config
from src.models.database import (
    get_db,
    Listing,
    CalendarObservation,
    DailyMarketMetric,
    CollectionRun,
    init_db
)
from src.models.schema import NaturalLanguageQueryRequest, NaturalLanguageQueryResponse
from src.pipeline.collector import MarketCollector, normalize_slot
from src.agent.analyzer import MarketAnalysisAgent
from src.reporting.daily_report import DailyReportGenerator
from src.scheduler.runner import market_scheduler
import pytz

IST = pytz.timezone("Asia/Kolkata")

def get_ist_today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def resolve_slot_for_date(db: Session, date: str, requested_slot: Optional[str] = None) -> str:
    if requested_slot and requested_slot.lower() not in ("latest", "all", "none", ""):
        return normalize_slot(requested_slot)
    row = (
        db.query(DailyMarketMetric.snapshot_slot)
        .filter(DailyMarketMetric.observation_date == date)
        .order_by(DailyMarketMetric.id.desc())
        .first()
    )
    if row and row[0]:
        return row[0]
    return "manual"

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(
    title=settings.app_name,
    description="Ahmedabad Airbnb Market Daily Tracker for Lease Model Evaluation",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Static and Templates
static_dir = BASE_DIR / "static"
static_dir.mkdir(parents=True, exist_ok=True)
(static_dir / "css").mkdir(parents=True, exist_ok=True)
(static_dir / "js").mkdir(parents=True, exist_ok=True)

templates_dir = BASE_DIR / "templates"
templates_dir.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))


@app.on_event("startup")
def startup_event():
    init_db()
    if settings.scheduler_enabled and not market_scheduler.scheduler.running:
        market_scheduler.start()


@app.on_event("shutdown")
def shutdown_event():
    market_scheduler.shutdown()



@app.get("/", response_class=HTMLResponse)
def index_view(request: Request):
    m_cfg = load_market_config()
    return templates.TemplateResponse(
        name="index.html",
        request=request,
        context={
            "city": m_cfg.city,
            "areas": m_cfg.areas,
            "collection_time": m_cfg.collection_time_ist,
            "timezone": m_cfg.timezone,
        }
    )


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": settings.app_name, "time": datetime.utcnow().isoformat()}


@app.get("/api/scheduler/jobs")
@app.get("/api/scheduler/status")
def get_scheduler_status():
    return market_scheduler.get_status()


@app.post("/api/scheduler/schedule-interval")
def schedule_interval_trigger(
    minutes: int = Query(5, ge=1, le=1440, description="Interval in minutes"),
    delay_minutes: int = Query(2, ge=0, le=1440, description="Delay before first run in minutes"),
):
    result = market_scheduler.schedule_interval_job(minutes=minutes, delay_minutes=delay_minutes)
    return {"status": "SUCCESS", "scheduler": result}



@app.get("/api/config")
def get_market_configuration():
    return load_market_config().dict()


@app.get("/api/areas")
def get_discovered_areas():
    cfg = load_market_config()
    return {
        "city": cfg.city,
        "count": len(cfg.areas),
        "areas": cfg.areas
    }


@app.get("/api/available-slots")
def get_available_slots(
    date: Optional[str] = Query(None, description="Observation date YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    if not date:
        latest = db.query(DailyMarketMetric.observation_date).order_by(desc(DailyMarketMetric.observation_date)).first()
        date = latest[0] if latest else get_ist_today()

    rows = (
        db.query(DailyMarketMetric.snapshot_slot)
        .filter(DailyMarketMetric.observation_date == date)
        .distinct()
        .all()
    )
    slots_found = [r[0] for r in rows if r[0]]
    ordered_standard = ["4pm", "8pm", "11.30pm", "manual"]
    available_slots = [s for s in ordered_standard if s in slots_found] + [s for s in slots_found if s not in ordered_standard]
    
    latest_slot_row = (
        db.query(DailyMarketMetric.snapshot_slot)
        .filter(DailyMarketMetric.observation_date == date)
        .order_by(DailyMarketMetric.id.desc())
        .first()
    )
    latest_slot = latest_slot_row[0] if latest_slot_row else "manual"

    return {
        "observation_date": date,
        "available_slots": available_slots,
        "latest_slot": latest_slot,
        "all_supported_slots": ["4pm", "8pm", "11.30pm", "manual"]
    }


@app.get("/api/overview")
def get_market_overview(
    date: Optional[str] = Query(None, description="Observation date YYYY-MM-DD"),
    area: Optional[str] = Query("Ahmedabad", description="Area or 'Ahmedabad' overall"),
    slot: Optional[str] = Query(None, description="Snapshot slot: 4pm, 8pm, 11.30pm, manual, or latest"),
    db: Session = Depends(get_db)
):
    # If date not specified, get latest
    if not date:
        latest = db.query(DailyMarketMetric.observation_date).order_by(desc(DailyMarketMetric.observation_date)).first()
        date = latest[0] if latest else get_ist_today()

    target_slot = resolve_slot_for_date(db, date, slot)
    target_area = area or "Ahmedabad"
    is_latest_query = not slot or slot.lower() in ("latest", "all", "none", "")

    metric = (
        db.query(DailyMarketMetric)
        .filter(
            DailyMarketMetric.observation_date == date,
            DailyMarketMetric.snapshot_slot == target_slot,
            DailyMarketMetric.area == target_area
        )
        .first()
    )

    if not metric and is_latest_query:
        # Fallback to target area without slot restriction ONLY when 'latest' was requested
        metric = (
            db.query(DailyMarketMetric)
            .filter(DailyMarketMetric.observation_date == date, DailyMarketMetric.area == target_area)
            .order_by(DailyMarketMetric.id.desc())
            .first()
        )
        if not metric:
            metric = db.query(DailyMarketMetric).filter(DailyMarketMetric.observation_date == date).order_by(DailyMarketMetric.id.desc()).first()

    # Calculate exact forward horizons (Tonight 1D, 7D, 14D, 30D)
    horizons = {}
    if metric:
        try:
            from datetime import timedelta
            obs_dt = datetime.strptime(date, "%Y-%m-%d")
            d1 = date
            d2 = (obs_dt + timedelta(days=1)).strftime("%Y-%m-%d")
            d3 = (obs_dt + timedelta(days=2)).strftime("%Y-%m-%d")
            d7 = (obs_dt + timedelta(days=6)).strftime("%Y-%m-%d")
            d14 = (obs_dt + timedelta(days=13)).strftime("%Y-%m-%d")
            d30 = (obs_dt + timedelta(days=29)).strftime("%Y-%m-%d")

            q = db.query(CalendarObservation.calendar_date, CalendarObservation.status, CalendarObservation.price).filter(
                CalendarObservation.observation_date == date,
                CalendarObservation.snapshot_slot == target_slot
            )
            if target_area != "Ahmedabad":
                q = q.join(Listing, CalendarObservation.listing_id == Listing.listing_id).filter(Listing.area == target_area)

            rows = q.all()
            if not rows and is_latest_query:
                q_fallback = db.query(CalendarObservation.calendar_date, CalendarObservation.status, CalendarObservation.price).filter(
                    CalendarObservation.observation_date == date
                )
                if target_area != "Ahmedabad":
                    q_fallback = q_fallback.join(Listing, CalendarObservation.listing_id == Listing.listing_id).filter(Listing.area == target_area)
                rows = q_fallback.all()

            def calc_h_stats(subset, label, date_range):
                if not subset:
                    return None
                unavail = sum(1 for r in subset if r[1] in ("unavailable", "blocked", "booked"))
                rate = round(unavail / len(subset), 4)
                prices = [r[2] for r in subset if r[2] and r[2] > 0]
                default_adr = round(float(getattr(metric, "adr", 3200.0) or 3200.0), 2) if metric else 3200.0
                adr = round(sum(prices) / len(prices), 2) if prices else default_adr
                return {
                    "label": label,
                    "date_range": date_range,
                    "total_nights": len(subset),
                    "unavailable_nights": unavail,
                    "available_nights": max(0, len(subset) - unavail),
                    "unavailability_rate": rate,
                    "adr": adr,
                    "revpar_proxy": round(adr * rate, 2)
                }

            horizons = {
                "tonight_1d": calc_h_stats([r for r in rows if r[0] == d1], "Tonight (1 Night)", f"{d1}"),
                "next_2d": calc_h_stats([r for r in rows if d1 <= r[0] <= d2], "Next 2 Days", f"{d1} to {d2}"),
                "next_3d": calc_h_stats([r for r in rows if d1 <= r[0] <= d3], "Next 3 Days", f"{d1} to {d3}"),
                "next_7d": calc_h_stats([r for r in rows if d1 <= r[0] <= d7], "Next 7 Days", f"{d1} to {d7}"),
            }
        except Exception:
            horizons = {}

    return {
        "city": settings.market_config.city,
        "selected_area": target_area,
        "observation_date": date,
        "snapshot_slot": target_slot,
        "has_data": metric is not None,
        "metric": metric.to_dict() if metric else None,
        "horizons": horizons,
    }


@app.get("/api/comparison")
def get_area_comparison(
    date: Optional[str] = Query(None, description="Observation date YYYY-MM-DD"),
    slot: Optional[str] = Query(None, description="Snapshot slot: 4pm, 8pm, 11.30pm, manual, or latest"),
    db: Session = Depends(get_db)
):
    if not date:
        latest = db.query(DailyMarketMetric.observation_date).order_by(desc(DailyMarketMetric.observation_date)).first()
        date = latest[0] if latest else get_ist_today()

    target_slot = resolve_slot_for_date(db, date, slot)
    is_latest_query = not slot or slot.lower() in ("latest", "all", "none", "")

    rows = (
        db.query(DailyMarketMetric)
        .filter(
            DailyMarketMetric.observation_date == date,
            DailyMarketMetric.snapshot_slot == target_slot,
            DailyMarketMetric.area != "Ahmedabad"
        )
        .order_by(DailyMarketMetric.active_listings.desc())
        .all()
    )
    if not rows and is_latest_query:
        rows = (
            db.query(DailyMarketMetric)
            .filter(DailyMarketMetric.observation_date == date, DailyMarketMetric.area != "Ahmedabad")
            .order_by(DailyMarketMetric.active_listings.desc())
            .all()
        )

    return {
        "observation_date": date,
        "snapshot_slot": target_slot,
        "areas": [r.to_dict() for r in rows]
    }


@app.get("/api/trends")
def get_market_trends(
    area: Optional[str] = Query("Ahmedabad", description="Tracked area or Ahmedabad overall"),
    slot: Optional[str] = Query(None, description="Snapshot slot: 4pm, 8pm, 11.30pm, manual, or latest"),
    days: int = Query(90, ge=7, le=365),
    db: Session = Depends(get_db)
):
    target_area = area or "Ahmedabad"
    q = db.query(DailyMarketMetric).filter(DailyMarketMetric.area == target_area)
    if slot and slot.lower() not in ("latest", "all", ""):
        norm_slot = normalize_slot(slot)
        q = q.filter(DailyMarketMetric.snapshot_slot == norm_slot)

    rows = q.order_by(DailyMarketMetric.observation_date.desc(), DailyMarketMetric.id.desc()).all()

    # Deduplicate: if slot is 'latest' or unspecified, return at most 1 metric per observation_date (latest)
    seen_dates = set()
    deduped = []
    for r in rows:
        if r.observation_date not in seen_dates:
            seen_dates.add(r.observation_date)
            deduped.append(r)
        if len(deduped) >= days:
            break

    # Reverse to chronological order for charts
    ordered = list(reversed(deduped))
    return {
        "area": target_area,
        "snapshot_slot": slot or "latest",
        "data": [r.to_dict() for r in ordered]
    }


@app.get("/api/listings")
def get_listings(
    area: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(True),
    search: Optional[str] = Query(None, description="Search by listing ID, title, or area"),
    date: Optional[str] = Query(None, description="Observation date YYYY-MM-DD for occupancy calculations"),
    slot: Optional[str] = Query(None, description="Snapshot slot: 4pm, 8pm, 11.30pm, manual, or latest"),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    from sqlalchemy import or_

    query = db.query(Listing)
    if area and area != "Ahmedabad":
        query = query.filter(Listing.area == area)
    if is_active is not None:
        query = query.filter(Listing.is_active == is_active)
    
    if search:
        search_clean = search.strip()
        # If user pasted an Airbnb room URL, extract the ID
        if "/rooms/" in search_clean:
            import re
            m = re.search(r'/rooms/(\d+)', search_clean)
            if m:
                search_clean = m.group(1)

        query = query.filter(
            or_(
                Listing.listing_id.ilike(f"%{search_clean}%"),
                Listing.title.ilike(f"%{search_clean}%"),
                Listing.area.ilike(f"%{search_clean}%")
            )
        )
        total = query.count()
        results = query.order_by(Listing.review_count.desc()).limit(limit).all()

        # If not found in DB and search_clean looks like an Airbnb listing ID (digits or length >= 6):
        if not results and (search_clean.isdigit() or len(search_clean) >= 6):
            try:
                from src.providers.direct_web import DirectWebAirbnbProvider
                provider = DirectWebAirbnbProvider()
                details = provider.get_listing_details(search_clean)
                if details:
                    now_dt = datetime.utcnow()
                    new_l = Listing(
                        listing_id=details.listing_id,
                        title=details.title,
                        area=details.area,
                        property_type=details.property_type,
                        room_type=details.room_type,
                        bedrooms=details.bedrooms,
                        beds=details.beds,
                        bathrooms=details.bathrooms,
                        rating=details.rating,
                        review_count=details.review_count,
                        first_seen_at=now_dt,
                        last_seen_at=now_dt,
                        is_active=True,
                        source="AIRBNB_LIVE_SEARCH",
                        listing_url=details.listing_url or f"https://www.airbnb.com/rooms/{details.listing_id}"
                    )
                    db.merge(new_l)
                    db.commit()
                    results = [new_l]
                    total = 1
            except Exception as e:
                logger.error(f"Live listing search error for {search_clean}: {e}")
    else:
        total = query.count()
        results = query.order_by(Listing.review_count.desc()).limit(limit).all()

    # Determine observation date and slot for forward horizon occupancy calculation
    if not date:
        latest = db.query(DailyMarketMetric.observation_date).order_by(desc(DailyMarketMetric.observation_date)).first()
        date = latest[0] if latest else get_ist_today()

    target_slot = resolve_slot_for_date(db, date, slot)
    is_latest_query = not slot or slot.lower() in ("latest", "all", "none", "")

    obs_dt = datetime.strptime(date, "%Y-%m-%d")
    d1 = date
    d2 = (obs_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    d3 = (obs_dt + timedelta(days=2)).strftime("%Y-%m-%d")
    d7_list = [(obs_dt + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    l_ids = [l.listing_id for l in results]
    cal_rows = (
        db.query(CalendarObservation.listing_id, CalendarObservation.calendar_date, CalendarObservation.status)
        .filter(
            CalendarObservation.listing_id.in_(l_ids),
            CalendarObservation.observation_date == date,
            CalendarObservation.snapshot_slot == target_slot
        )
        .all()
    )
    # If no cal_rows for this slot, fallback to any slot ONLY when 'latest' was requested
    if not cal_rows and is_latest_query:
        cal_rows = (
            db.query(CalendarObservation.listing_id, CalendarObservation.calendar_date, CalendarObservation.status)
            .filter(CalendarObservation.listing_id.in_(l_ids), CalendarObservation.observation_date == date)
            .all()
        )

    cal_by_id = {}
    for lid, c_dt, stat in cal_rows:
        cal_by_id.setdefault(lid, {})[c_dt] = stat

    listings_data = []
    for l in results:
        item = l.to_dict()
        d_map = cal_by_id.get(l.listing_id, {})
        u1 = 1 if d_map.get(d1) in ("unavailable", "booked", "blocked") else 0
        u2 = sum(1 for dt in [d1, d2] if d_map.get(dt) in ("unavailable", "booked", "blocked"))
        u3 = sum(1 for dt in [d1, d2, d3] if d_map.get(dt) in ("unavailable", "booked", "blocked"))
        u7 = sum(1 for dt in d7_list if d_map.get(dt) in ("unavailable", "booked", "blocked"))
        item["occ_1d"] = f"{u1}/1"
        item["occ_2d"] = f"{u2}/2"
        item["occ_3d"] = f"{u3}/3"
        item["occ_7d"] = f"{u7}/7"
        item["occ_1d_val"] = u1
        item["occ_2d_val"] = u2
        item["occ_3d_val"] = u3
        item["occ_7d_val"] = u7
        listings_data.append(item)

    return {
        "total": total,
        "returned": len(listings_data),
        "observation_date": date,
        "snapshot_slot": target_slot,
        "listings": listings_data
    }


@app.get("/api/runs")
def get_collection_runs(
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db)
):
    runs = db.query(CollectionRun).order_by(desc(CollectionRun.started_at)).limit(limit).all()
    return {"runs": [r.to_dict() for r in runs]}


@app.get("/api/daily-report")
def get_daily_report(
    date: Optional[str] = Query(None),
    slot: Optional[str] = Query(None, description="Snapshot slot: 4pm, 8pm, 11.30pm, manual, or latest"),
    db: Session = Depends(get_db)
):
    rep_gen = DailyReportGenerator(db)
    rep_date = date or get_ist_today()
    report_text = rep_gen.generate_report(rep_date, snapshot_slot=slot)
    return {
        "observation_date": rep_date,
        "snapshot_slot": slot or "latest",
        "report": report_text
    }


def run_collection_background_task(
    obs_date: str,
    slot: str,
    provider: Optional[str] = None,
    fetch_calendars: bool = False
):
    try:
        collector = MarketCollector(
            observation_date=obs_date,
            provider_name=provider,
            fetch_individual_calendars=fetch_calendars,
            snapshot_slot=slot
        )
        return collector.run()
    except Exception as e:
        import logging
        logging.getLogger("airbnbanalyzer").error(f"Background collection error for slot {slot}: {e}", exc_info=True)


@app.get("/api/trigger-collection")
@app.post("/api/trigger-collection")
def trigger_daily_collection(
    background_tasks: BackgroundTasks,
    date: Optional[str] = Query(None),
    slot: Optional[str] = Query("manual", description="Snapshot slot: 4pm, 8pm, 11.30pm, manual"),
    provider: Optional[str] = Query(None),
    fetch_calendars: Optional[bool] = Query(False),
    background: Optional[bool] = Query(False, description="Run collection asynchronously in background"),
    async_mode: Optional[bool] = Query(False, alias="async", description="Run collection asynchronously in background"),
    db: Session = Depends(get_db)
):
    obs_date = date.strip() if date and date.strip() else get_ist_today()
    norm_slot = normalize_slot(slot)

    # 1. Prevent concurrent duplicate runs if an ingestion for this slot started within last 4 minutes
    four_min_ago = datetime.utcnow() - timedelta(minutes=4)
    active_run = (
        db.query(CollectionRun)
        .filter(
            CollectionRun.observation_date == obs_date,
            CollectionRun.snapshot_slot == norm_slot,
            CollectionRun.status == "RUNNING",
            CollectionRun.started_at >= four_min_ago
        )
        .first()
    )
    if active_run:
        return {
            "status": "ALREADY_RUNNING",
            "message": f"An ingestion run for slot [{norm_slot}] on {obs_date} is already actively running.",
            "run_id": active_run.run_id,
            "started_at": active_run.started_at.isoformat() if active_run.started_at else None,
            "observation_date": obs_date,
            "snapshot_slot": norm_slot
        }

    # 2. Async / Background execution mode
    if background or async_mode:
        background_tasks.add_task(
            run_collection_background_task,
            obs_date=obs_date,
            slot=norm_slot,
            provider=provider,
            fetch_calendars=bool(fetch_calendars)
        )
        return {
            "status": "QUEUED",
            "message": f"Collection task started in background for slot [{norm_slot}] on {obs_date}.",
            "observation_date": obs_date,
            "snapshot_slot": norm_slot
        }

    # 3. Synchronous execution mode (used by UI button)
    collector = MarketCollector(
        db=db,
        observation_date=obs_date,
        provider_name=provider,
        fetch_individual_calendars=fetch_calendars,
        snapshot_slot=norm_slot
    )
    result = collector.run()
    return result


@app.post("/api/admin/cleanup-date")
def cleanup_observation_date(
    date: str = Query(..., description="Observation date YYYY-MM-DD to remove"),
    slot: Optional[str] = Query(None, description="Optional slot to remove, or all slots if omitted"),
    db: Session = Depends(get_db)
):
    cal_q = db.query(CalendarObservation).filter(CalendarObservation.observation_date == date)
    metric_q = db.query(DailyMarketMetric).filter(DailyMarketMetric.observation_date == date)
    run_q = db.query(CollectionRun).filter(CollectionRun.observation_date == date)

    if slot and slot.lower() not in ("all", "*", ""):
        norm_slot = normalize_slot(slot)
        cal_q = cal_q.filter(CalendarObservation.snapshot_slot == norm_slot)
        metric_q = metric_q.filter(DailyMarketMetric.snapshot_slot == norm_slot)
        run_q = run_q.filter(CollectionRun.snapshot_slot == norm_slot)

    del_cal = cal_q.delete(synchronize_session=False)
    del_metric = metric_q.delete(synchronize_session=False)
    del_runs = run_q.delete(synchronize_session=False)
    db.commit()

    return {
        "status": "SUCCESS",
        "date": date,
        "slot": slot or "all",
        "deleted_calendar_observations": del_cal,
        "deleted_metrics": del_metric,
        "deleted_runs": del_runs,
    }


@app.post("/api/ai-query", response_model=NaturalLanguageQueryResponse)
def execute_natural_language_query(
    payload: NaturalLanguageQueryRequest,
    db: Session = Depends(get_db)
):
    agent = MarketAnalysisAgent(db)
    res = agent.answer_query(payload.query)
    return NaturalLanguageQueryResponse(**res)


class UpdateCurlRequest(BaseModel):
    curl: str


@app.post("/api/auth/update-curl")
def update_auth_from_curl(payload: UpdateCurlRequest):
    from src.providers.session_manager import session_manager
    session_data = session_manager.update_from_curl(payload.curl)
    return {
        "status": "SUCCESS",
        "cookies_count": len(session_data.get("cookies", {})),
        "api_key": session_data.get("api_key"),
        "updated_at": session_data.get("updated_at"),
    }


@app.post("/api/auth/refresh-session")
def refresh_guest_session():
    from src.providers.session_manager import session_manager
    session_data = session_manager.bootstrap_guest_session()
    return {
        "status": "SUCCESS",
        "cookies_count": len(session_data.get("cookies", {})),
        "api_key": session_data.get("api_key"),
        "updated_at": session_data.get("updated_at"),
    }

