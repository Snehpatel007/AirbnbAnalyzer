"""
Reassign all listings to their true geographic areas using coordinates and recalculate daily metrics.
"""
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import settings
from src.models.database import Listing, DailyMarketMetric, CalendarObservation
from src.pipeline.geocoder import geocoder
from src.pipeline.aggregator import DailyAggregator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    db = Session()

    listings = db.query(Listing).all()
    logger.info(f"Re-evaluating {len(listings)} listings with Ahmedabad Area Geocoder...")

    reassigned_count = 0
    in_scope_count = 0
    excluded_count = 0

    for l in listings:
        old_area = l.area
        resolved_area, is_in_scope = geocoder.resolve_listing_area(
            listing_id=l.listing_id,
            title=l.title,
            lat=l.latitude,
            lon=l.longitude,
            fallback_area=old_area
        )

        if not is_in_scope:
            l.is_active = False
            l.area = "Outside Ahmedabad"
            excluded_count += 1
        else:
            l.is_active = True
            l.area = resolved_area
            in_scope_count += 1
            if resolved_area != old_area:
                reassigned_count += 1

    db.commit()
    logger.info(f"Geocoding complete! In-scope: {in_scope_count}, Excluded out-of-city: {excluded_count}, Reassigned to true area: {reassigned_count}")

    # Now recalculate daily market metrics for 2026-10-04 and 2026-10-05
    dates = ["2026-10-04", "2026-10-05"]
    areas = settings.market_config.areas

    for obs_date in dates:
        logger.info(f"Recalculating market metrics for {obs_date}...")
        db.query(DailyMarketMetric).filter(DailyMarketMetric.observation_date == obs_date).delete()
        db.commit()

        aggregator = DailyAggregator(db, observation_date=obs_date)
        area_metrics = []

        for area in areas:
            listings_in_area = db.query(Listing).filter(Listing.area == area, Listing.is_active == True).count()
            m = aggregator.calculate_for_area(area, expected_listings=listings_in_area, observed_listings=listings_in_area)
            db.add(m)
            area_metrics.append(m)

        db.commit()
        total_active = sum(m.active_listings for m in area_metrics)
        city_m = aggregator.calculate_city_overall(area_metrics, expected_total=total_active, observed_total=total_active)
        db.add(city_m)
        db.commit()

        logger.info(f"  {obs_date} Metrics -> Active: {city_m.active_listings}, 1D Unavailability: {city_m.unavailability_1d*100:.1f}%, 7D: {city_m.unavailability_7d*100:.1f}%")

    db.close()
    logger.info("Area reassignment and recalculation successfully finished!")


if __name__ == "__main__":
    main()
