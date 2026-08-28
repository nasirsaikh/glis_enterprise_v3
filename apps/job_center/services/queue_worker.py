from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from apps.job_center.models import QueuedJob
from apps.job_center.registry import get_job_handler

def process_queue(batch_size=10):
    processed = 0
    while processed < batch_size:
        job = claim_next_job()
        if not job:
            break
        execute_queued_job(job)
        processed += 1
    return processed

def claim_next_job():
    with transaction.atomic():
        job = (QueuedJob.objects.select_for_update(skip_locked=True).filter(status=QueuedJob.Status.PENDING,run_after__lte=timezone.now(),)
            .order_by(
                "priority",
                "run_after",
                "pk",
            )
            .first()
        )

        if not job:
            return None

        job.status = QueuedJob.Status.RUNNING
        job.locked_at = timezone.now()
        job.started_at = timezone.now()
        job.attempts += 1

        job.save(
            update_fields=[
                "status",
                "locked_at",
                "started_at",
                "attempts",
            ]
        )

        return job


def execute_queued_job(job):

    try:

        handler = get_job_handler(
            job.handler
        )

        result = handler(
            **(job.parameters or {})
        )

        job.status = QueuedJob.Status.SUCCESS
        job.result = (
            result
            if isinstance(result, dict)
            else {"result": str(result)}
        )

        job.finished_at = timezone.now()
        job.error = ""

        job.save(
            update_fields=[
                "status",
                "result",
                "finished_at",
                "error",
            ]
        )

    except Exception as exc:

        job.error = str(exc)

        if job.attempts < job.max_attempts:

            job.status = QueuedJob.Status.PENDING

            job.run_after = (
                timezone.now()
                + timedelta(
                    seconds=job.retry_delay_seconds
                )
            )

        else:

            job.status = QueuedJob.Status.FAILED
            job.finished_at = timezone.now()

        job.save()