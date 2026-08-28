# Generated manually for the portable Job Center package.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SchedulerLock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True)),
                ("owner", models.CharField(blank=True, max_length=255)),
                ("heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Scheduler Lock",
                "verbose_name_plural": "Scheduler Locks",
            },
        ),
        migrations.CreateModel(
            name="ScheduledJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200, unique=True)),
                ("description", models.TextField(blank=True)),
                ("job_type", models.CharField(choices=[("PYTHON", "Python Function"), ("SQL", "SQL Query"), ("STORED_PROCEDURE", "Stored Procedure"), ("HTTP", "HTTP / API")], default="PYTHON", max_length=30)),
                ("handler", models.CharField(blank=True, help_text="Registered handler name, e.g. reports.daily_claims.", max_length=255)),
                ("parameters", models.JSONField(blank=True, default=dict)),
                ("database_alias", models.CharField(blank=True, help_text="Django DATABASES alias. Leave blank to use 'default'.", max_length=100)),
                ("sql_query", models.TextField(blank=True)),
                ("stored_procedure", models.CharField(blank=True, max_length=255)),
                ("http_url", models.URLField(blank=True)),
                ("http_method", models.CharField(blank=True, default="GET", max_length=10)),
                ("http_headers", models.JSONField(blank=True, default=dict)),
                ("http_body", models.JSONField(blank=True, default=dict)),
                ("cron_expression", models.CharField(default="0 0 * * *", help_text="5-part cron: minute hour day-of-month month day-of-week", max_length=100)),
                ("timezone", models.CharField(default="Asia/Muscat", max_length=100)),
                ("enabled", models.BooleanField(default=True)),
                ("max_instances", models.PositiveIntegerField(default=1)),
                ("timeout_seconds", models.PositiveIntegerField(default=3600)),
                ("retry_count", models.PositiveIntegerField(default=0)),
                ("retry_delay_seconds", models.PositiveIntegerField(default=60)),
                ("misfire_grace_seconds", models.PositiveIntegerField(default=300)),
                ("coalesce", models.BooleanField(default=True)),
                ("last_run_at", models.DateTimeField(blank=True, null=True)),
                ("next_run_at", models.DateTimeField(blank=True, null=True)),
                ("last_status", models.CharField(blank=True, max_length=30)),
                ("last_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="job_center_created_jobs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Scheduled Job",
                "verbose_name_plural": "Scheduled Jobs",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="JobExecution",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("QUEUED", "Queued"), ("RUNNING", "Running"), ("SUCCESS", "Success"), ("FAILED", "Failed"), ("TIMEOUT", "Timeout"), ("CANCELLED", "Cancelled"), ("MISSED", "Missed")], default="QUEUED", max_length=20)),
                ("trigger_type", models.CharField(choices=[("SCHEDULED", "Scheduled"), ("MANUAL", "Manual"), ("RETRY", "Retry"), ("API", "API")], default="SCHEDULED", max_length=20)),
                ("attempt", models.PositiveIntegerField(default=1)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("duration_seconds", models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True)),
                ("parameters", models.JSONField(blank=True, default=dict)),
                ("result", models.JSONField(blank=True, null=True)),
                ("output", models.TextField(blank=True)),
                ("error", models.TextField(blank=True)),
                ("traceback", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="executions", to="job_center.scheduledjob")),
                ("triggered_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="job_center_triggered_executions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Job Execution",
                "verbose_name_plural": "Job Executions",
                "ordering": ["-created_at"],
            },
        ),
    ]
