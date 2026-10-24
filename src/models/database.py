from datetime import datetime
from typing import Generator
import pytz
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Float,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Text,
    Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from config.settings import settings

Base = declarative_base()


class Listing(Base):
    __tablename__ = "listings"

    listing_id = Column(String(64), primary_key=True, index=True)
    title = Column(String(256), nullable=True)
    area = Column(String(128), nullable=False, index=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    property_type = Column(String(128), nullable=True)
    room_type = Column(String(128), nullable=True)
    bedrooms = Column(Integer, default=2)
    beds = Column(Integer, default=2)
    bathrooms = Column(Float, default=1.0)
    has_wifi = Column(Boolean, default=True, nullable=False)
    has_ac = Column(Boolean, default=True, nullable=False)
    rating = Column(Float, nullable=True)
    review_count = Column(Integer, default=0)
    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    source = Column(String(64), default="AIRBNB_OBSERVED", nullable=False)
    listing_url = Column(String(512), nullable=True)

    calendar_observations = relationship("CalendarObservation", back_populates="listing", cascade="all, delete-orphan")

    @property
    def airbnb_url(self) -> str:
        if self.listing_url:
            return self.listing_url
        if self.listing_id:
            clean_id = self.listing_id.replace("airbnb_", "").replace("ab_", "")
            return f"https://www.airbnb.com/rooms/{clean_id}"
        return ""

    def to_dict(self):
        return {
            "listing_id": self.listing_id,
            "title": self.title,
            "area": self.area,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "property_type": self.property_type,
            "room_type": self.room_type,
            "bedrooms": self.bedrooms,
            "beds": self.beds,
            "bathrooms": self.bathrooms,
            "has_wifi": self.has_wifi,
            "has_ac": self.has_ac,
            "rating": self.rating,
            "review_count": self.review_count,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "is_active": self.is_active,
            "source": self.source,
            "listing_url": self.airbnb_url,
        }


class CalendarObservation(Base):
    __tablename__ = "calendar_observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    listing_id = Column(String(64), ForeignKey("listings.listing_id", ondelete="CASCADE"), nullable=False, index=True)
    observation_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    calendar_date = Column(String(10), nullable=False, index=True)     # YYYY-MM-DD
    status = Column(String(32), nullable=False)  # available, booked, blocked, unavailable, unknown
    bookable = Column(Boolean, default=False, nullable=False)
    price = Column(Float, nullable=True)  # Nightly base rate excluding one-time fees
    minimum_stay = Column(Integer, default=1)
    raw_status = Column(String(64), nullable=True)
    source = Column(String(64), default="AIRBNB_OBSERVED", nullable=False)
    snapshot_slot = Column(String(16), default="manual", nullable=False, index=True)  # 4pm, 8pm, 11.30pm, manual

    listing = relationship("Listing", back_populates="calendar_observations")

    __table_args__ = (
        UniqueConstraint("listing_id", "calendar_date", "observation_date", "snapshot_slot", name="uix_listing_cal_obs_slot"),
        Index("idx_obs_area_date_slot", "observation_date", "snapshot_slot", "calendar_date"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "listing_id": self.listing_id,
            "observation_date": self.observation_date,
            "snapshot_slot": self.snapshot_slot,
            "calendar_date": self.calendar_date,
            "status": self.status,
            "bookable": self.bookable,
            "price": self.price,
            "minimum_stay": self.minimum_stay,
            "raw_status": self.raw_status,
            "source": self.source,
        }


class DailyMarketMetric(Base):
    __tablename__ = "daily_market_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    observation_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    snapshot_slot = Column(String(16), default="manual", nullable=False, index=True)  # 4pm, 8pm, 11.30pm, manual
    area = Column(String(128), nullable=False, index=True)  # "Ahmedabad" or specific area name
    active_listings = Column(Integer, default=0, nullable=False)
    available_listing_nights = Column(Integer, default=0, nullable=False)
    unavailable_listing_nights = Column(Integer, default=0, nullable=False)
    booked_listing_nights = Column(Integer, default=0, nullable=False)
    observed_unavailability_rate = Column(Float, nullable=False)  # unavailable / total_calendar_nights
    booking_occupancy = Column(Float, nullable=True)  # Only set if confirmed booked status exists
    adr = Column(Float, nullable=False)  # Total nightly rates / eligible priced nights
    revpar_proxy = Column(Float, nullable=False)  # ADR * observed_unavailability_rate
    
    # Trend Detection
    active_listing_change_1d = Column(Integer, default=0)
    active_listing_change_7d = Column(Integer, default=0)
    active_listing_change_30d = Column(Integer, default=0)
    unavailability_change_1d_pp = Column(Float, default=0.0)  # Percentage point change
    unavailability_change_7d_pp = Column(Float, default=0.0)
    unavailability_change_30d_pp = Column(Float, default=0.0)
    
    coverage_rate = Column(Float, default=1.0, nullable=False)  # Successfully observed / expected active listings
    status = Column(String(32), default="COMPLETE", nullable=False)  # COMPLETE, PARTIAL, FAILED

    # Multi-Horizon Matrix (Tonight 1D, Next 2 Days, Next 3 Days, Next 7 Days)
    unavailability_1d = Column(Float, nullable=True)
    unavailability_2d = Column(Float, nullable=True)
    unavailability_3d = Column(Float, nullable=True)
    unavailability_7d = Column(Float, nullable=True)

    adr_1d = Column(Float, nullable=True)
    adr_2d = Column(Float, nullable=True)
    adr_3d = Column(Float, nullable=True)
    adr_7d = Column(Float, nullable=True)

    revpar_1d = Column(Float, nullable=True)
    revpar_2d = Column(Float, nullable=True)
    revpar_3d = Column(Float, nullable=True)
    revpar_7d = Column(Float, nullable=True)

    nights_total_1d = Column(Integer, default=0)
    nights_unavail_1d = Column(Integer, default=0)
    nights_total_2d = Column(Integer, default=0)
    nights_unavail_2d = Column(Integer, default=0)
    nights_total_3d = Column(Integer, default=0)
    nights_unavail_3d = Column(Integer, default=0)
    nights_total_7d = Column(Integer, default=0)
    nights_unavail_7d = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("observation_date", "snapshot_slot", "area", name="uix_metric_obs_date_slot_area"),
        Index("idx_metric_area_date_slot", "area", "observation_date", "snapshot_slot"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "observation_date": self.observation_date,
            "snapshot_slot": self.snapshot_slot,
            "area": self.area,
            "active_listings": self.active_listings,
            "available_listing_nights": self.available_listing_nights,
            "unavailable_listing_nights": self.unavailable_listing_nights,
            "booked_listing_nights": self.booked_listing_nights,
            "observed_unavailability_rate": self.observed_unavailability_rate,
            "booking_occupancy": self.booking_occupancy,
            "adr": self.adr,
            "revpar_proxy": self.revpar_proxy,
            "unavailability_1d": self.unavailability_1d or self.observed_unavailability_rate,
            "unavailability_2d": self.unavailability_2d or self.observed_unavailability_rate,
            "unavailability_3d": self.unavailability_3d or self.observed_unavailability_rate,
            "unavailability_7d": self.unavailability_7d or self.observed_unavailability_rate,
            "adr_1d": self.adr_1d or self.adr,
            "adr_2d": self.adr_2d or self.adr,
            "adr_3d": self.adr_3d or self.adr,
            "adr_7d": self.adr_7d or self.adr,
            "revpar_1d": self.revpar_1d or self.revpar_proxy,
            "revpar_2d": self.revpar_2d or self.revpar_proxy,
            "revpar_3d": self.revpar_3d or self.revpar_proxy,
            "revpar_7d": self.revpar_7d or self.revpar_proxy,
            "nights_total_1d": self.nights_total_1d,
            "nights_unavail_1d": self.nights_unavail_1d,
            "nights_total_2d": self.nights_total_2d,
            "nights_unavail_2d": self.nights_unavail_2d,
            "nights_total_3d": self.nights_total_3d,
            "nights_unavail_3d": self.nights_unavail_3d,
            "nights_total_7d": self.nights_total_7d,
            "nights_unavail_7d": self.nights_unavail_7d,
            "active_listing_change_1d": self.active_listing_change_1d,
            "active_listing_change_7d": self.active_listing_change_7d,
            "active_listing_change_30d": self.active_listing_change_30d,
            "unavailability_change_1d_pp": self.unavailability_change_1d_pp,
            "unavailability_change_7d_pp": self.unavailability_change_7d_pp,
            "unavailability_change_30d_pp": self.unavailability_change_30d_pp,
            "coverage_rate": self.coverage_rate,
            "status": self.status,
        }


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    run_id = Column(String(64), primary_key=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    observation_date = Column(String(10), nullable=False, index=True)
    snapshot_slot = Column(String(16), default="manual", nullable=False, index=True)  # 4pm, 8pm, 11.30pm, manual
    status = Column(String(32), default="RUNNING", nullable=False)  # RUNNING, SUCCESS, PARTIAL, FAILED
    listings_discovered = Column(Integer, default=0)
    calendar_records_collected = Column(Integer, default=0)
    coverage_pct = Column(Float, default=0.0)
    errors = Column(Text, nullable=True)
    provider = Column(String(64), nullable=False)

    def to_dict(self):
        kolkata_tz = pytz.timezone(settings.market_config.timezone)
        started_ist = None
        completed_ist = None
        if self.started_at:
            dt = self.started_at
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            started_ist = dt.astimezone(kolkata_tz).strftime("%Y-%m-%d %H:%M:%S IST")
        if self.completed_at:
            dt = self.completed_at
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            completed_ist = dt.astimezone(kolkata_tz).strftime("%Y-%m-%d %H:%M:%S IST")

        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "started_at_ist": started_ist,
            "completed_at_ist": completed_ist,
            "observation_date": self.observation_date,
            "snapshot_slot": self.snapshot_slot,
            "status": self.status,
            "listings_discovered": self.listings_discovered,
            "calendar_records_collected": self.calendar_records_collected,
            "coverage_pct": self.coverage_pct,
            "errors": self.errors,
            "provider": self.provider,
        }


# Database Engine and Session Factory
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    echo=False
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
