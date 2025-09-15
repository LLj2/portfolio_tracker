import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from .. import performance, db

logger = logging.getLogger(__name__)

_scheduler = None

def start_scheduler(pricing_module):
    global _scheduler
    if _scheduler:
        return
    
    try:
        _scheduler = BackgroundScheduler(timezone="Europe/Athens")

        # Windowed runs (e.g., 12:00, 20:00)
        windows = os.getenv("SCHED_WINDOWS","12:00,20:00").split(",")
        for hhmm in windows:
            hh, mm = hhmm.strip().split(":")
            # Fix lambda closure issue by using partial
            from functools import partial
            _scheduler.add_job(
                partial(_run_prices, pricing_module), 
                CronTrigger(hour=int(hh), minute=int(mm))
            )

        # EOD snapshot
        eod = os.getenv("SCHED_EOD_TIME","23:30")
        eh, em = eod.split(":")
        _scheduler.add_job(_run_eod_snapshot, CronTrigger(hour=int(eh), minute=int(em)))

        _scheduler.start()
        logger.info(f"Scheduler started with windows: {windows}, EOD: {eod}")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        raise

def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None

def _run_prices(pricing_module):
    try:
        with db.SessionLocal() as s:
            pricing_module.run_price_cycle(s)
            s.commit()
            logger.info("Scheduled price update completed")
    except Exception as e:
        logger.error(f"Error in scheduled price update: {e}")

def _run_eod_snapshot():
    try:
        with db.SessionLocal() as s:
            performance.capture_eod_snapshots(s)
            s.commit()
            logger.info("EOD snapshot completed")
    except Exception as e:
        logger.error(f"Error in EOD snapshot: {e}")
