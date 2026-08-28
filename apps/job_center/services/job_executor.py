import json
import time
import traceback as traceback_module
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from django.db import close_old_connections, connections
from django.utils import timezone

from ..models import JobExecution, ScheduledJob
from ..registry import get_job_handler


def _json_safe(value):
    try:
        json.dumps(value, default=str)
        if isinstance(value, dict):
            return json.loads(json.dumps(value, default=str))
        return value
    except Exception:
        return str(value)


def execute_python_job(job: ScheduledJob):
    handler = get_job_handler(job.handler)
    return handler(**(job.parameters or {}))


def execute_sql_job(job: ScheduledJob):
    alias = job.database_alias or "default"
    connection = connections[alias]

    with connection.cursor() as cursor:
        cursor.execute(job.sql_query)

        if cursor.description is None:
            return {
                "success": True,
                "affected_rows": cursor.rowcount,
            }

        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

    preview_limit = 1000
    preview = [
        dict(zip(columns, row))
        for row in rows[:preview_limit]
    ]

    return {
        "success": True,
        "columns": columns,
        "row_count": len(rows),
        "preview_limited_to": preview_limit,
        "rows": _json_safe(preview),
    }


def execute_stored_procedure(job: ScheduledJob):
    alias = job.database_alias or "default"
    connection = connections[alias]
    params = job.parameters or {}

    with connection.cursor() as cursor:
        if params:
            placeholders = ", ".join(["%s"] * len(params))
            cursor.execute(
                f"EXEC {job.stored_procedure} {placeholders}",
                list(params.values()),
            )
        else:
            cursor.execute(f"EXEC {job.stored_procedure}")

        if cursor.description is None:
            return {
                "success": True,
                "affected_rows": cursor.rowcount,
            }

        columns = [column[0] for column in cursor.description]
        rows = cursor.fetchall()

    return {
        "success": True,
        "columns": columns,
        "row_count": len(rows),
        "rows": _json_safe([dict(zip(columns, row)) for row in rows[:1000]]),
    }


def execute_http_job(job: ScheduledJob):
    import urllib.request

    method = (job.http_method or "GET").upper()
    headers = job.http_headers or {}
    body = job.http_body or {}

    data = None
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json", **headers}

    request = urllib.request.Request(
        job.http_url,
        data=data,
        headers=headers,
        method=method,
    )

    with urllib.request.urlopen(request, timeout=job.timeout_seconds) as response:
        raw = response.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw

        return {
            "success": 200 <= response.status < 300,
            "status_code": response.status,
            "response": _json_safe(parsed),
        }


def _run_single(job: ScheduledJob):
    if job.job_type == ScheduledJob.JobType.PYTHON:
        return execute_python_job(job)

    if job.job_type == ScheduledJob.JobType.SQL:
        return execute_sql_job(job)

    if job.job_type == ScheduledJob.JobType.STORED_PROCEDURE:
        return execute_stored_procedure(job)

    if job.job_type == ScheduledJob.JobType.HTTP:
        return execute_http_job(job)

    raise NotImplementedError(f"Unsupported job type: {job.job_type}")


def _run_with_timeout(job: ScheduledJob):
    timeout = max(1, int(job.timeout_seconds or 3600))

    # Timeout prevents Job Center from waiting forever. Note that Python threads
    # cannot forcibly terminate arbitrary running Python code after timeout.
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_single, job)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError as exc:
            raise TimeoutError(
                f"Job exceeded timeout of {timeout} seconds."
            ) from exc


def execute_job(
    job_id: int,
    trigger_type=JobExecution.TriggerType.SCHEDULED,
    user_id=None,
):
    close_old_connections()

    job = ScheduledJob.objects.get(pk=job_id)
    max_attempts = max(1, int(job.retry_count or 0) + 1)

    last_exception = None

    for attempt in range(1, max_attempts + 1):
        started = timezone.now()

        execution = JobExecution.objects.create(
            job=job,
            status=JobExecution.Status.RUNNING,
            trigger_type=(
                trigger_type
                if attempt == 1
                else JobExecution.TriggerType.RETRY
            ),
            attempt=attempt,
            started_at=started,
            parameters=job.parameters or {},
            triggered_by_id=user_id,
        )

        try:
            result = _run_with_timeout(job)

            finished = timezone.now()
            duration = (finished - started).total_seconds()

            execution.status = JobExecution.Status.SUCCESS
            execution.finished_at = finished
            execution.duration_seconds = duration
            execution.result = _json_safe(result) if isinstance(result, dict) else None
            execution.output = "" if isinstance(result, dict) else str(result)
            execution.save()

            ScheduledJob.objects.filter(pk=job.pk).update(
                last_run_at=finished,
                last_status=JobExecution.Status.SUCCESS,
                last_message="Completed successfully.",
            )

            return result

        except TimeoutError as exc:
            last_exception = exc
            finished = timezone.now()

            execution.status = JobExecution.Status.TIMEOUT
            execution.finished_at = finished
            execution.duration_seconds = (finished - started).total_seconds()
            execution.error = str(exc)
            execution.traceback = traceback_module.format_exc()
            execution.save()

        except Exception as exc:
            last_exception = exc
            finished = timezone.now()

            execution.status = JobExecution.Status.FAILED
            execution.finished_at = finished
            execution.duration_seconds = (finished - started).total_seconds()
            execution.error = str(exc)
            execution.traceback = traceback_module.format_exc()
            execution.save()

        if attempt < max_attempts:
            time.sleep(max(0, int(job.retry_delay_seconds or 0)))

    final_status = (
        JobExecution.Status.TIMEOUT
        if isinstance(last_exception, TimeoutError)
        else JobExecution.Status.FAILED
    )

    ScheduledJob.objects.filter(pk=job.pk).update(
        last_run_at=timezone.now(),
        last_status=final_status,
        last_message=str(last_exception or "Job failed."),
    )

    if last_exception:
        raise last_exception
