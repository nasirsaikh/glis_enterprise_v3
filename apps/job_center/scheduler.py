import atexit
import logging
import threading

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django.db import close_old_connections

from .locks import (
    OWNER,
    heartbeat_seconds,
    refresh_lock,
    release_lock,
    try_acquire_lock,
)
from .models import JobExecution, ScheduledJob
from .services.job_executor import execute_job


from apscheduler.triggers.interval import (IntervalTrigger,)
from apps.job_center.services.queue_worker import process_queue

logger = logging.getLogger(__name__)

_scheduler = None
_scheduler_guard = threading.Lock()
_heartbeat_stop = threading.Event()
_heartbeat_thread = None


def get_scheduler():
    return _scheduler


def build_cron_trigger(job: ScheduledJob):
    parts = job.cron_expression.strip().split()
    if len(parts) != 5:
        raise ValueError(f"Invalid 5-part cron expression: {job.cron_expression}")
    minute, hour, day, month, weekday = parts
    return CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=weekday,
        timezone=job.timezone,
    )


def _scheduled_runner(job_id: int):
    execute_job(
        job_id=job_id,
        trigger_type=JobExecution.TriggerType.SCHEDULED,
    )


def sync_jobs():
    global _scheduler
    if _scheduler is None: return
    close_old_connections()
    enabled_jobs = list(ScheduledJob.objects.filter(enabled=True))
    expected_ids = set()
    for job in enabled_jobs:
        scheduler_id = f"job_center_schedule_{job.pk}"
        expected_ids.add(scheduler_id)
        trigger = build_cron_trigger(job)
        _scheduler.add_job(_scheduled_runner, trigger=trigger, id=scheduler_id, name=job.name, args=[job.pk], replace_existing=True, max_instances=max(1, int(job.max_instances or 1)), coalesce=bool(job.coalesce), misfire_grace_time=max(1, int(job.misfire_grace_seconds or 300)))
        aps_job = _scheduler.get_job(scheduler_id)
        if aps_job: ScheduledJob.objects.filter(pk=job.pk).update(next_run_at=aps_job.next_run_time)
    for aps_job in _scheduler.get_jobs():
        if aps_job.id.startswith("job_center_schedule_") and aps_job.id not in expected_ids: _scheduler.remove_job(aps_job.id)
    ScheduledJob.objects.filter(enabled=False).update(next_run_at=None)

def run_job_now(job_id: int, user_id=None):
    if _scheduler is None:
        raise RuntimeError("Job Center scheduler is not running in this process.")

    _scheduler.add_job(
        execute_job,
        id=f"manual_{job_id}_{threading.get_ident()}_{id(object())}",
        args=[
            job_id,
            JobExecution.TriggerType.MANUAL,
            user_id,
        ],
        replace_existing=False,
    )


def _heartbeat_loop():
    global _scheduler

    interval = heartbeat_seconds()

    while not _heartbeat_stop.wait(interval):
        close_old_connections()

        try:
            if not refresh_lock():
                logger.warning(
                    "Job Center lost scheduler leadership. Stopping scheduler."
                )
                if _scheduler is not None:
                    _scheduler.shutdown(wait=False)
                    _scheduler = None
                return
        except Exception:
            logger.exception("Job Center scheduler heartbeat failed.")


def start_scheduler():
    global _scheduler, _heartbeat_thread

    with _scheduler_guard:
        if _scheduler is not None:
            return True

        try:
            if not try_acquire_lock():
                logger.info(
                    "Job Center scheduler not started: another process owns the leader lock."
                )
                return False
        except Exception:
            logger.exception("Job Center could not acquire scheduler leader lock.")
            return False

        max_workers = int(getattr(settings, "JOB_CENTER_MAX_WORKERS", 10))

        scheduler = BackgroundScheduler(
            timezone=getattr(settings, "TIME_ZONE", "Asia/Muscat"),
            executors={
                "default": ThreadPoolExecutor(max_workers=max_workers),
            },
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 300,
            },
        )
        scheduler.start()
        scheduler.add_job(process_queue, trigger=IntervalTrigger(seconds=5), id="_job_center_queue_worker", name="Job Center Queue Worker", replace_existing=True, max_instances=1, coalesce=True)
        _scheduler = scheduler
        try:
            sync_jobs()
        except Exception:
            logger.exception("Job Center initial synchronization failed.")

        _heartbeat_stop.clear()
        _heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name="job-center-heartbeat",
            daemon=True,
        )
        _heartbeat_thread.start()

        logger.info("Job Center scheduler started. Leader owner=%s", OWNER)
        return True


def stop_scheduler():
    global _scheduler

    _heartbeat_stop.set()

    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            logger.exception("Error while shutting down Job Center scheduler.")
        finally:
            _scheduler = None

    try:
        release_lock()
    except Exception:
        logger.exception("Error while releasing Job Center scheduler lock.")


atexit.register(stop_scheduler)
