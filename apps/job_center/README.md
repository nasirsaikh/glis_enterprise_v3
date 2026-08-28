# GLIS Job Center

A lightweight Hangfire-style background job and scheduler app for Django.

## What it provides

- No Redis / RabbitMQ
- No Celery worker
- No Celery Beat
- No separate scheduler management command
- APScheduler embedded in Django startup
- Database-backed leader lock to reduce duplicate scheduling across multiple Django workers
- Cron schedules
- Python function jobs
- SQL query jobs
- Stored procedure jobs
- HTTP/API jobs
- Manual "Run now"
- Retry handling
- Timeout recording
- Execution history
- Error + traceback logging
- Django Admin UI
- Basic staff-only API endpoints

## 1. Install dependency

```bash
pip install "APScheduler>=3.10,<4"
```

Add to requirements.txt:

```text
APScheduler>=3.10,<4
```

## 2. Copy the app

Recommended GLIS location:

```text
apps/job_center/
```

If you place this package under `apps/job_center`, change `apps.py`:

```python
name = "apps.job_center"
```

and use:

```python
"apps.job_center.apps.JobCenterConfig",
```

in `INSTALLED_APPS`.

If you place it at project root as `job_center/`, use the files exactly as supplied.

## 3. Settings

Add:

```python
INSTALLED_APPS += [
    "apps.job_center.apps.JobCenterConfig",
]

JOB_CENTER_ENABLED = True
JOB_CENTER_MAX_WORKERS = 10
JOB_CENTER_LOCK_TTL_SECONDS = 90
JOB_CENTER_HEARTBEAT_SECONDS = 30

TIME_ZONE = "Asia/Muscat"
USE_TZ = True
```

For local troubleshooting you can temporarily disable startup:

```python
JOB_CENTER_ENABLED = False
```

## 4. URLs

Optional, only needed for the included APIs:

```python
path("job-center/", include("apps.job_center.urls")),
```

The Django Admin functionality works without these URLs.

## 5. Migrations

```bash
python manage.py migrate
```

A portable `0001_initial.py` migration is included.

If your project reports migration-state conflicts, delete only the included migration file and run:

```bash
python manage.py makemigrations job_center
python manage.py migrate
```

## 6. Register Python jobs

Edit:

```text
apps/job_center/jobs/examples.py
```

or add your own modules.

Example:

```python
from apps.job_center.registry import register_job

@register_job("reports.daily_claims")
def daily_claims(**kwargs):
    # Call existing GLIS service code here.
    return {"success": True}
```

Then import that module from:

```text
apps/job_center/jobs/__init__.py
```

Create a Scheduled Job in Django Admin:

- Type: Python Function
- Handler: `reports.daily_claims`
- Cron: `0 7 * * 1-5`

## 7. SQL Server job

If settings.py contains:

```python
DATABASES = {
    "default": {...},
    "premia": {...},
}
```

create:

- Type: SQL Query
- Database alias: `premia`
- SQL query: your query
- Cron: e.g. `0 7 * * 1-5`

## Cron examples

```text
0 7 * * *       Every day 07:00
0 7 * * 1-5     Monday-Friday 07:00
*/15 * * * *    Every 15 minutes
0 */2 * * *     Every 2 hours
0 2 * * 0       Sunday 02:00
30 23 28 * *    28th of every month 23:30
```

## Production warning

This package includes a DB-backed scheduler leader lock so that only one Django process should become scheduler leader.

However, an embedded scheduler lives inside your web application process. If your hosting platform frequently kills/restarts all web processes, scheduled jobs cannot run while no Django process exists.

For ordinary GLIS deployment on a continuously running IIS/Waitress/Gunicorn service, this design fits the "no separate command/broker" requirement well.

## Timeout limitation

The current implementation records a timeout if a Python job exceeds its configured timeout. Python cannot safely force-kill an arbitrary running thread.

For genuinely untrusted or very CPU-heavy jobs, use a process-isolated execution model later.

## Security

Do not expose arbitrary Python source code through Admin.

Use the registry pattern instead:

```python
@register_job("safe.name")
def safe_function(...):
    ...
```

For SQL jobs, restrict Job Center Admin access to trusted staff because an SQL job has whatever permissions are granted to its configured database connection.

## Suggested GLIS integrations

Good candidates:

- MIS SQL extracts
- Email reports
- Excel generation
- PPTX generation
- SSRS-related extraction
- Vanna/Ollama refresh jobs
- Notification dispatch
- Data cleanup
- Reconciliation jobs
- Claims / policy dashboards
