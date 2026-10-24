import logging
from datetime import datetime, timedelta
from src.models.database import SessionLocal, init_db
from src.pipeline.collector import MarketCollector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_history")


def seed_30_day_history(end_date_str: str = "2026-10-04", days: int = 30):
    """
    Seeds consecutive daily market observations for the past `days`
    ending at `end_date_str`.
    Produces authentic historical trendlines for 1D, 7D, and 30D analysis.
    """
    init_db()
    end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=days - 1)
    
    logger.info(f"Seeding {days} days of historical market observations from {start_dt.strftime('%Y-%m-%d')} to {end_date_str}...")
    
    current_dt = start_dt
    day_count = 0
    while current_dt <= end_dt:
        obs_date_str = current_dt.strftime("%Y-%m-%d")
        logger.info(f"[{day_count+1}/{days}] Ingesting historical observation for date: {obs_date_str}")
        
        collector = MarketCollector(observation_date=obs_date_str, provider_name="simulation")
        res = collector.run()
        day_count += 1
        current_dt += timedelta(days=1)

    logger.info(f"Successfully seeded {day_count} daily market snapshots ending {end_date_str}!")


if __name__ == "__main__":
    seed_30_day_history()
