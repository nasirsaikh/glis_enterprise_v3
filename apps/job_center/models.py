from django.conf import settings
from django.db import models


class QueuedJob(models.Model):

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RUNNING = "RUNNING", "Running"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    handler = models.CharField(
        max_length=255,
    )

    parameters = models.JSONField(
        default=dict,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    priority = models.PositiveSmallIntegerField(
        default=5,
        db_index=True,
    )

    run_after = models.DateTimeField(
        db_index=True,
    )

    attempts = models.PositiveIntegerField(
        default=0,
    )

    max_attempts = models.PositiveIntegerField(
        default=3,
    )

    retry_delay_seconds = models.PositiveIntegerField(
        default=60,
    )

    locked_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    finished_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    result = models.JSONField(
        null=True,
        blank=True,
    )

    error = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "priority",
            "run_after",
            "created_at",
        ]
        indexes = [
            models.Index(
                fields=[
                    "status",
                    "run_after",
                ]
            )
        ]

    def __str__(self):
        return f"{self.handler} #{self.pk}"

class ScheduledJob(models.Model):
    class JobType(models.TextChoices):
        PYTHON = "PYTHON", "Python Function"
        SQL = "SQL", "SQL Query"
        STORED_PROCEDURE = "STORED_PROCEDURE", "Stored Procedure"
        HTTP = "HTTP", "HTTP / API"

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    job_type = models.CharField(max_length=30, choices=JobType.choices, default=JobType.PYTHON)

    handler = models.CharField(
        max_length=255,
        blank=True,
        help_text="Registered handler name, e.g. reports.daily_claims.",
    )
    parameters = models.JSONField(default=dict, blank=True)

    database_alias = models.CharField(
        max_length=100,
        blank=True,
        help_text="Django DATABASES alias. Leave blank to use 'default'.",
    )
    sql_query = models.TextField(blank=True)
    stored_procedure = models.CharField(max_length=255, blank=True)

    http_url = models.URLField(blank=True)
    http_method = models.CharField(max_length=10, default="GET", blank=True)
    http_headers = models.JSONField(default=dict, blank=True)
    http_body = models.JSONField(default=dict, blank=True)

    cron_expression = models.CharField(
        max_length=100,
        default="0 0 * * *",
        help_text="5-part cron: minute hour day-of-month month day-of-week",
    )
    timezone = models.CharField(max_length=100, default="Asia/Muscat")

    enabled = models.BooleanField(default=True)
    max_instances = models.PositiveIntegerField(default=1)
    timeout_seconds = models.PositiveIntegerField(default=3600)
    retry_count = models.PositiveIntegerField(default=0)
    retry_delay_seconds = models.PositiveIntegerField(default=60)
    misfire_grace_seconds = models.PositiveIntegerField(default=300)
    coalesce = models.BooleanField(default=True)

    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=30, blank=True)
    last_message = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="job_center_created_jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Scheduled Job"
        verbose_name_plural = "Scheduled Jobs"

    def __str__(self):
        return self.name


class JobExecution(models.Model):
    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        RUNNING = "RUNNING", "Running"
        SUCCESS = "SUCCESS", "Success"
        FAILED = "FAILED", "Failed"
        TIMEOUT = "TIMEOUT", "Timeout"
        CANCELLED = "CANCELLED", "Cancelled"
        MISSED = "MISSED", "Missed"

    class TriggerType(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        MANUAL = "MANUAL", "Manual"
        RETRY = "RETRY", "Retry"
        API = "API", "API"

    job = models.ForeignKey(ScheduledJob, on_delete=models.CASCADE, related_name="executions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    trigger_type = models.CharField(max_length=20, choices=TriggerType.choices, default=TriggerType.SCHEDULED)

    attempt = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)

    parameters = models.JSONField(default=dict, blank=True)
    result = models.JSONField(null=True, blank=True)
    output = models.TextField(blank=True)
    error = models.TextField(blank=True)
    traceback = models.TextField(blank=True)

    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="job_center_triggered_executions",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Job Execution"
        verbose_name_plural = "Job Executions"

    def __str__(self):
        return f"{self.job.name} - {self.status} - #{self.pk}"


class SchedulerLock(models.Model):
    name = models.CharField(max_length=100, unique=True)
    owner = models.CharField(max_length=255, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Scheduler Lock"
        verbose_name_plural = "Scheduler Locks"

    def __str__(self):
        return self.name
