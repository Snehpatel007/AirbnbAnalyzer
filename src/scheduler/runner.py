import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz
from config.settings import settings
from src.pipeline.collector import MarketCollector

logger = logging.getLogger("airbnbanalyzer.scheduler")


def scheduled_slot_ingestion(slot: str = "manual"):
    """
    Job executed automatically on schedule for a specific collection slot:
    '4pm' (16:00 IST), '8pm' (20:00 IST), '11.30pm' (23:30 IST), or 'manual'.
    """
    kolkata_tz = pytz.timezone(settings.market_config.timezone)
    now_ist = datetime.now(kolkata_tz)
    today_str = now_ist.strftime("%Y-%m-%d")
    
    logger.info(f"Starting scheduled {slot} Airbnb ingestion for {today_str} at {now_ist.strftime('%H:%M:%S %Z')}...")
    try:
        collector = MarketCollector(observation_date=today_str, snapshot_slot=slot)
        result = collector.run()
        logger.info(f"Scheduled {slot} collection run completed successfully: {result}")
        return result
    except Exception as e:
        logger.error(f"Error during scheduled {slot} collection: {e}", exc_info=True)
        return None


def scheduled_daily_ingestion():
    return scheduled_slot_ingestion("manual")


class MarketScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.timezone = pytz.timezone(settings.market_config.timezone)

    def start(self, auto_catchup: bool = False):
        if self.scheduler.running:
            logger.info("MarketScheduler is already running.")
            return

        # Slot 1: 4:00 PM IST (16:00)
        self.scheduler.add_job(
            scheduled_slot_ingestion,
            args=["4pm"],
            trigger=CronTrigger(hour=16, minute=0, timezone=self.timezone),
            id="cron_4pm_collector",
            name="Daily 4:00 PM IST Ingestion (4pm Slot)",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )

        # Slot 2: 8:00 PM IST (20:00)
        self.scheduler.add_job(
            scheduled_slot_ingestion,
            args=["8pm"],
            trigger=CronTrigger(hour=20, minute=0, timezone=self.timezone),
            id="cron_8pm_collector",
            name="Daily 8:00 PM IST Ingestion (8pm Slot)",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )

        # Slot 3: 11:30 PM IST (23:30)
        self.scheduler.add_job(
            scheduled_slot_ingestion,
            args=["11.30pm"],
            trigger=CronTrigger(hour=23, minute=30, timezone=self.timezone),
            id="cron_11_30pm_collector",
            name="Daily 11:30 PM IST Ingestion (11.30pm Slot)",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )

        self.scheduler.start()
        logger.info(
            f"MarketScheduler started with 3 daily scheduled ingestion runs: 4:00 PM, 8:00 PM, and 11:30 PM {settings.market_config.timezone}."
        )

    def schedule_interval_job(self, minutes: int = 5, delay_minutes: int = 2):
        """
        Dynamically schedule or adjust an interval ingestion job.
        """
        start_time = datetime.now(self.timezone) + timedelta(minutes=delay_minutes)
        job = self.scheduler.add_job(
            scheduled_daily_ingestion,
            trigger=IntervalTrigger(minutes=minutes, start_date=start_time, timezone=self.timezone),
            id="interval_5min_collector",
            name=f"{minutes}-Minute Automated Market Ingestion",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(f"Scheduled {minutes}-minute interval job starting at {start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        return {
            "job_id": job.id,
            "interval_minutes": minutes,
            "first_run_ist": start_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "next_run_iso": job.next_run_time.isoformat() if job.next_run_time else None,
        }

    def get_status(self):
        """
        Return the real-time operational status and next fire times of all scheduled jobs.
        """
        now = datetime.now(self.timezone)
        jobs_list = []
        if self.scheduler.running:
            for job in self.scheduler.get_jobs():
                next_run = job.next_run_time
                seconds_left = round((next_run - now).total_seconds()) if next_run else None
                jobs_list.append({
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": next_run.strftime("%Y-%m-%d %H:%M:%S %Z") if next_run else None,
                    "next_run_iso": next_run.isoformat() if next_run else None,
                    "seconds_until_next_run": seconds_left,
                    "trigger": str(job.trigger),
                })
        return {
            "scheduler_running": self.scheduler.running,
            "current_time_ist": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "jobs_count": len(jobs_list),
            "jobs": jobs_list,
        }

    def _check_today_catchup(self, target_hour: int, target_minute: int):
        """
        If the server is started after 9:00 AM IST and today's snapshot
        has not been captured yet, run an immediate catchup collection.
        """
        try:
            from src.models.database import SessionLocal, DailyMarketMetric
            now_ist = datetime.now(self.timezone)
            target_time = now_ist.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            today_str = now_ist.strftime("%Y-%m-%d")

            if now_ist >= target_time:
                with SessionLocal() as db:
                    existing_today = (
                        db.query(DailyMarketMetric)
                        .filter(DailyMarketMetric.observation_date == today_str)
                        .first()
                    )
                if not existing_today:
                    logger.info(f"Current time ({now_ist.strftime('%H:%M %Z')}) is past 9 AM IST and no snapshot found for {today_str}. Triggering background catchup collection...")
                    self.scheduler.add_job(
                        scheduled_daily_ingestion,
                        id="today_catchup_collector",
                        name="Catchup Today Airbnb Ingestion",
                        replace_existing=True
                    )
                else:
                    logger.info(f"Today's ({today_str}) market snapshot already exists in database. No catchup needed.")
        except Exception as ex:
            logger.warning(f"Could not verify today's snapshot status: {ex}")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("MarketScheduler shutdown.")


market_scheduler = MarketScheduler()

