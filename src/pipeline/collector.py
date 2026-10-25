import uuid
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from config.settings import settings, load_market_config
from src.models.database import (
    SessionLocal,
    Listing,
    CalendarObservation,
    DailyMarketMetric,
    CollectionRun,
    init_db
)
from src.models.schema import RawListing, RawCalendarDay
from src.providers.factory import get_data_provider
from src.pipeline.validator import DataQualityValidator
from src.pipeline.aggregator import DailyAggregator
from src.pipeline.geocoder import geocoder
import pytz

IST = pytz.timezone("Asia/Kolkata")

def get_ist_today() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def normalize_slot(slot: Optional[str]) -> str:
    if not slot:
        return "manual"
    s = str(slot).strip().lower()
    if s in ("4pm", "16:00", "16", "4:00pm", "4:00", "4"):
        return "4pm"
    if s in ("8pm", "20:00", "20", "8:00pm", "8:00", "8"):
        return "8pm"
    if s in ("11.30pm", "11:30pm", "23:30", "11:30", "11.30"):
        return "11.30pm"
    return "manual"


class MarketCollector:
    """
    Orchestrates the Ahmedabad Airbnb daily collection pipeline.
    Executes listing discovery, master listing updates, calendar snapshot,
    data validation, metric aggregation, and collection run audit.
    Supports distinct snapshot slots: '4pm', '8pm', '11.30pm', 'manual'.
    """

    def __init__(
        self,
        db: Optional[Session] = None,
        observation_date: Optional[str] = None,
        provider_name: Optional[str] = None,
        fetch_individual_calendars: Optional[bool] = None,
        snapshot_slot: Optional[str] = "manual",
    ):
        self.db = db or SessionLocal()
        self._owns_db = db is None
        self.observation_date = (
            observation_date.strip()
            if observation_date and str(observation_date).strip()
            else get_ist_today()
        )
        self.snapshot_slot = normalize_slot(snapshot_slot)
        self.provider = get_data_provider(provider_type=provider_name, observation_date=self.observation_date)
        self.horizon_days = settings.market_config.calendar_horizon_days
        self.inactivity_days = settings.market_config.inactivity_days_threshold
        self.fetch_individual_calendars = (
            fetch_individual_calendars
            if fetch_individual_calendars is not None
            else getattr(settings, "fetch_individual_calendars", False)
        )

    def run(self) -> Dict:
        init_db()
        run_id = str(uuid.uuid4())
        started_at = datetime.utcnow()
        provider_name = self.provider.get_provider_name()
        
        # Initialize collection run audit record
        run_record = CollectionRun(
            run_id=run_id,
            started_at=started_at,
            observation_date=self.observation_date,
            snapshot_slot=self.snapshot_slot,
            status="RUNNING",
            provider=provider_name,
        )
        self.db.add(run_record)
        self.db.commit()

        total_discovered = 0
        total_calendar_records = 0
        errors: List[str] = []
        area_metrics: List[DailyMarketMetric] = []
        expected_listings_total = 0
        observed_listings_total = 0

        try:
            city_name = settings.market_config.city
            print(f"Discovering listings across {city_name} map bounds...", flush=True)

            # 1. Discover listings across metropolitan map square
            if hasattr(self.provider, "search_by_map_bounds"):
                raw_listings = self.provider.search_by_map_bounds(max_pages=8)
            else:
                raw_listings = self.provider.search_listings(city_name)

            if not raw_listings:
                areas = load_market_config().areas
                for area in areas:
                    raw_listings.extend(self.provider.search_listings(area, page=1, page_size=-1))

            if hasattr(self.provider, "get_last_errors"):
                p_errs = self.provider.get_last_errors()
                if p_errs:
                    errors.extend(p_errs)

            valid_listings, val_errs = DataQualityValidator.validate_listings(raw_listings)
            errors.extend(val_errs)

            expected_listings_total = max(len(raw_listings), 1)
            observed_listings_total = len(valid_listings)
            total_discovered = observed_listings_total

            # 2. Master Listing Update & Area Resolution
            now_dt = datetime.utcnow()
            active_listings_by_area: Dict[str, List[str]] = {}
            all_active_listing_ids: List[str] = []

            for raw_l in valid_listings:
                resolved_area, is_in_scope = geocoder.resolve_listing_area(
                    listing_id=raw_l.listing_id,
                    title=raw_l.title,
                    lat=raw_l.latitude,
                    lon=raw_l.longitude,
                    fallback_area=raw_l.area or "SG Highway"
                )

                existing = self.db.query(Listing).filter(Listing.listing_id == raw_l.listing_id).first()
                url = getattr(raw_l, "listing_url", None) or f"https://www.airbnb.com/rooms/{raw_l.listing_id.replace('airbnb_', '').replace('ab_', '')}"
                if existing:
                    existing.title = raw_l.title or existing.title
                    existing.area = resolved_area
                    existing.latitude = raw_l.latitude or existing.latitude
                    existing.longitude = raw_l.longitude or existing.longitude
                    existing.property_type = raw_l.property_type or existing.property_type
                    existing.room_type = raw_l.room_type or existing.room_type
                    existing.bedrooms = raw_l.bedrooms or existing.bedrooms
                    existing.beds = getattr(raw_l, "beds", existing.beds or 2)
                    existing.bathrooms = raw_l.bathrooms or existing.bathrooms
                    existing.has_wifi = getattr(raw_l, "has_wifi", True)
                    existing.has_ac = getattr(raw_l, "has_ac", True)
                    existing.rating = raw_l.rating or existing.rating
                    existing.review_count = raw_l.review_count or existing.review_count
                    existing.listing_url = url
                    existing.last_seen_at = now_dt
                    existing.is_active = is_in_scope
                else:
                    new_listing = Listing(
                        listing_id=raw_l.listing_id,
                        title=raw_l.title,
                        area=resolved_area,
                        latitude=raw_l.latitude,
                        longitude=raw_l.longitude,
                        property_type=raw_l.property_type,
                        room_type=raw_l.room_type,
                        bedrooms=raw_l.bedrooms,
                        beds=getattr(raw_l, "beds", 2),
                        bathrooms=raw_l.bathrooms,
                        has_wifi=getattr(raw_l, "has_wifi", True),
                        has_ac=getattr(raw_l, "has_ac", True),
                        rating=raw_l.rating,
                        review_count=raw_l.review_count,
                        first_seen_at=now_dt,
                        last_seen_at=now_dt,
                        is_active=is_in_scope,
                        source=raw_l.source,
                        listing_url=url,
                    )
                    self.db.add(new_listing)

                if is_in_scope:
                    all_active_listing_ids.append(raw_l.listing_id)
                    active_listings_by_area.setdefault(resolved_area, []).append(raw_l.listing_id)

            self.db.commit()

            # Dynamic Areas generation
            discovered_areas = sorted(list(active_listings_by_area.keys()))
            if discovered_areas:
                from config.settings import CONFIG_PATH
                try:
                    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                        json.dump({"city": city_name, "areas": discovered_areas}, f, indent=2)
                except Exception as e:
                    logger.warning(f"Could not update {CONFIG_PATH}: {e}")

            # 3. Calendar Snapshot for ALL active listings in metro
            listing_price_map = {l.listing_id: l.nightly_price for l in valid_listings}

            if all_active_listing_ids:
                self.db.query(CalendarObservation).filter(
                    CalendarObservation.listing_id.in_(all_active_listing_ids),
                    CalendarObservation.observation_date == self.observation_date,
                    CalendarObservation.snapshot_slot == self.snapshot_slot
                ).delete(synchronize_session=False)
                self.db.commit()

            if hasattr(self.provider, "get_horizon_calendar_by_date_search") and not self.fetch_individual_calendars:
                print(f"⚡ Date-by-Date Map Ingestion: Fetching 7-day availability for {len(all_active_listing_ids)} listings without individual calendar calls...", flush=True)
                bulk_days = self.provider.get_horizon_calendar_by_date_search(
                    master_listing_ids=all_active_listing_ids,
                    start_date=self.observation_date,
                    horizon_days=self.horizon_days,
                    listing_base_prices=listing_price_map,
                )
            elif hasattr(self.provider, "get_bulk_calendar"):
                print(f"Collecting live calendars for {len(all_active_listing_ids)} active listings via individual PdpAvailabilityCalendar API...", flush=True)
                bulk_days = self.provider.get_bulk_calendar(all_active_listing_ids, horizon_days=self.horizon_days, max_workers=4)
            else:
                bulk_days = {lid: self.provider.get_calendar(lid, horizon_days=self.horizon_days) for lid in all_active_listing_ids}

            new_calendar_obs = []
            seen_keys = set()
            for lid in all_active_listing_ids:
                cal_days = bulk_days.get(lid, [])
                valid_days, day_errs = DataQualityValidator.validate_calendar_days(cal_days, self.observation_date)
                errors.extend(day_errs)

                for day in valid_days:
                    key = (lid, day.calendar_date)
                    if key not in seen_keys:
                        seen_keys.add(key)
                        new_calendar_obs.append({
                            "listing_id": lid,
                            "observation_date": self.observation_date,
                            "calendar_date": day.calendar_date,
                            "status": day.status,
                            "bookable": day.bookable,
                            "price": day.price,
                            "minimum_stay": day.minimum_stay,
                            "raw_status": day.raw_status,
                            "source": day.source,
                        })
                        total_calendar_records += 1

            if new_calendar_obs:
                # Remove prior calendar records for THIS observation date and THIS snapshot slot
                self.db.query(CalendarObservation).filter(
                    CalendarObservation.observation_date == self.observation_date,
                    CalendarObservation.snapshot_slot == self.snapshot_slot
                ).delete()
                self.db.commit()
                for obs in new_calendar_obs:
                    obs["snapshot_slot"] = self.snapshot_slot
                self.db.bulk_insert_mappings(CalendarObservation, new_calendar_obs)
                self.db.commit()

            # 4. Calculate Area Metrics
            aggregator = DailyAggregator(self.db, self.observation_date, snapshot_slot=self.snapshot_slot)
            for area, lids in active_listings_by_area.items():
                area_metric = aggregator.calculate_for_area(area, len(lids), len(lids))
                existing_metric = (
                    self.db.query(DailyMarketMetric)
                    .filter(
                        DailyMarketMetric.observation_date == self.observation_date,
                        DailyMarketMetric.snapshot_slot == self.snapshot_slot,
                        DailyMarketMetric.area == area
                    )
                    .first()
                )
                if existing_metric:
                    for k, v in area_metric.to_dict().items():
                        if k not in ("id", "observation_date", "snapshot_slot", "area"):
                            setattr(existing_metric, k, v)
                    area_metrics.append(existing_metric)
                else:
                    self.db.add(area_metric)
                    area_metrics.append(area_metric)
            self.db.commit()

            # 5. Mark inactive listings that haven't been seen for inactivity_days
            cutoff_dt = datetime.utcnow() - timedelta(days=self.inactivity_days)
            self.db.query(Listing).filter(Listing.last_seen_at < cutoff_dt).update({"is_active": False})
            self.db.commit()

            # 6. Overall Metropolitan & City Metrics
            city_metric = aggregator.calculate_city_overall(
                area_metrics, expected_listings_total, observed_listings_total
            )
            city_labels = list(dict.fromkeys([city_name, "Ahmedabad", "Ahmedabad & Gandhinagar"]))
            for city_label in city_labels:
                existing_city = (
                    self.db.query(DailyMarketMetric)
                    .filter(
                        DailyMarketMetric.observation_date == self.observation_date,
                        DailyMarketMetric.snapshot_slot == self.snapshot_slot,
                        DailyMarketMetric.area == city_label
                    )
                    .first()
                )
                if existing_city:
                    for k, v in city_metric.to_dict().items():
                        if k not in ("id", "observation_date", "snapshot_slot", "area"):
                            setattr(existing_city, k, v)
                else:
                    new_m = DailyMarketMetric(**city_metric.to_dict())
                    new_m.area = city_label
                    new_m.snapshot_slot = self.snapshot_slot
                    self.db.add(new_m)
                self.db.commit()

            # 7. Finalize Collection Run Audit
            coverage_pct = round((observed_listings_total / max(1, expected_listings_total)) * 100.0, 2)
            run_status = "SUCCESS" if coverage_pct >= 95.0 and len(errors) == 0 else "PARTIAL"
            if observed_listings_total == 0:
                run_status = "FAILED"
                if not errors:
                    errors.append("No listings discovered: check network connectivity or Airbnb session authentication.")

            run_record.completed_at = datetime.utcnow()
            run_record.status = run_status
            run_record.listings_discovered = total_discovered
            run_record.calendar_records_collected = total_calendar_records
            run_record.coverage_pct = coverage_pct
            run_record.errors = json.dumps(errors[:50]) if errors else None
            self.db.commit()

            return {
                "run_id": run_id,
                "observation_date": self.observation_date,
                "snapshot_slot": self.snapshot_slot,
                "status": run_status,
                "provider": provider_name,
                "listings_discovered": total_discovered,
                "calendar_records": total_calendar_records,
                "coverage_pct": coverage_pct,
                "errors_count": len(errors),
            }

        except Exception as ex:
            self.db.rollback()
            run_record.completed_at = datetime.utcnow()
            run_record.status = "FAILED"
            run_record.errors = json.dumps([str(ex)])
            self.db.commit()
            raise ex
        finally:
            if self._owns_db:
                self.db.close()
