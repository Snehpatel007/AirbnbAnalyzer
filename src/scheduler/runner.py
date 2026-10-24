import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz
from config.settings import settings
from src.pipeline.collector import MarketCollector

logger = logging.getLogger("airbnbanalyzer.scheduler")


def scheduled_daily_ingestion():
    """
    Job executed automatically on schedule (Daily 9 AM IST and active interval runs).
    """
    kolkata_tz = pytz.timezone(settings.market_config.timezone)
    now_ist = datetime.now(kolkata_tz)
    today_str = now_ist.strftime("%Y-%m-%d")
    
    logger.info(f"Starting scheduled Airbnb ingestion for {today_str} at {now_ist.strftime('%H:%M:%S %Z')}...")
    try:
        collector = MarketCollector(observation_date=today_str)
        result = collector.run()
        logger.info(f"Scheduled collection run completed successfully: {result}")
        return result
    except Exception as e:
        logger.error(f"Error during scheduled collection: {e}", exc_info=True)
        return None


class MarketScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.timezone = pytz.timezone(settings.market_config.timezone)

    def start(self, auto_catchup: bool = True):
        if self.scheduler.running:
            logger.info("MarketScheduler is already running.")
            return

        hour, minute = [int(p) for p in settings.market_config.collection_time_ist.split(":")]
        trigger = CronTrigger(
            hour=hour,
            minute=minute,
            timezone=self.timezone
        )
        self.scheduler.add_job(
            scheduled_daily_ingestion,
            trigger=trigger,
            id="daily_airbnb_collector",
            name=f"Daily {hour:02d}:{minute:02d} IST Ahmedabad Airbnb Ingestion",
            replace_existing=True,
            misfire_grace_time=86400  # 24 hours grace time
        )
        self.scheduler.start()
        logger.info(
            f"MarketScheduler started. Single daily ingestion scheduled at {hour:02d}:{minute:02d} {settings.market_config.timezone} everyday. All other auto triggers removed."
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

