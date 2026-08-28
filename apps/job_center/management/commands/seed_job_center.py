from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import JobExecution, ScheduledJob


class Command(BaseCommand):
    help = "Seed sample Job Center scheduled jobs and execution history."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete previously seeded sample jobs before recreating them.",
        )
        parser.add_argument(
            "--with-history",
            action="store_true",
            help="Create sample JobExecution history records.",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            ScheduledJob.objects.filter(
                name__startswith="[Sample]"
            ).delete()
            self.stdout.write(
                self.style.WARNING("Existing sample Job Center data deleted.")
            )

        samples = [
            {
                "name": "[Sample] GLIS Scheduler Test",
                "description": (
                    "Simple Python test job. Safe to run manually from Django Admin."
                ),
                "job_type": ScheduledJob.JobType.PYTHON,
                "handler": "system.test_job",
                "parameters": {
                    "message": "GLIS Job Center scheduler is working successfully."
                },
                "cron_expression": "*/15 * * * *",
                "timezone": "Asia/Muscat",
                "enabled": True,
                "max_instances": 1,
                "timeout_seconds": 60,
                "retry_count": 1,
                "retry_delay_seconds": 10,
            },
            {
                "name": "[Sample] Daily Policy Count",
                "description": (
                    "Example SQL query using the Django default database. "
                    "Replace SQL and database alias with your GLIS/PREMIA datasource."
                ),
                "job_type": ScheduledJob.JobType.SQL,
                "database_alias": "default",
                "sql_query": (
                    "SELECT 1 AS sample_value"
                ),
                "parameters": {},
                "cron_expression": "0 7 * * 1-5",
                "timezone": "Asia/Muscat",
                "enabled": False,
                "max_instances": 1,
                "timeout_seconds": 300,
                "retry_count": 1,
                "retry_delay_seconds": 30,
            },
            {
                "name": "[Sample] Daily Claims MIS",
                "description": (
                    "Template for a SQL Server claims extract. "
                    "Set database_alias to your configured SQL Server alias "
                    "and replace the SQL with your actual query."
                ),
                "job_type": ScheduledJob.JobType.SQL,
                "database_alias": "premia",
                "sql_query": (
                    "SELECT TOP 100\n"
                    "    CLAIM_NO,\n"
                    "    POLICY_NO,\n"
                    "    CLAIM_STATUS\n"
                    "FROM CLAIMS\n"
                    "WHERE CLAIM_STATUS = 'OPEN'\n"
                    "ORDER BY CLAIM_NO DESC"
                ),
                "parameters": {},
                "cron_expression": "0 6 * * 1-5",
                "timezone": "Asia/Muscat",
                "enabled": False,
                "max_instances": 1,
                "timeout_seconds": 900,
                "retry_count": 2,
                "retry_delay_seconds": 60,
            },
            {
                "name": "[Sample] Monthly Stored Procedure",
                "description": (
                    "Template stored-procedure execution. "
                    "Update alias, procedure name, and parameters before enabling."
                ),
                "job_type": ScheduledJob.JobType.STORED_PROCEDURE,
                "database_alias": "premia",
                "stored_procedure": "dbo.usp_GenerateMonthlyMIS",
                "parameters": {
                    "department": "MOTOR",
                    "include_closed": False,
                },
                "cron_expression": "0 5 1 * *",
                "timezone": "Asia/Muscat",
                "enabled": False,
                "max_instances": 1,
                "timeout_seconds": 1800,
                "retry_count": 1,
                "retry_delay_seconds": 120,
            },
            {
                "name": "[Sample] Internal API Health Check",
                "description": (
                    "Example HTTP/API background job. "
                    "Update the URL before enabling."
                ),
                "job_type": ScheduledJob.JobType.HTTP,
                "http_url": "http://127.0.0.1:8000/",
                "http_method": "GET",
                "http_headers": {},
                "http_body": {},
                "parameters": {},
                "cron_expression": "*/30 * * * *",
                "timezone": "Asia/Muscat",
                "enabled": False,
                "max_instances": 1,
                "timeout_seconds": 30,
                "retry_count": 2,
                "retry_delay_seconds": 15,
            },
            {
                "name": "[Sample] Weekly AI Refresh",
                "description": (
                    "Template Python job for Vanna/Ollama refresh. "
                    "Register the handler before enabling this job."
                ),
                "job_type": ScheduledJob.JobType.PYTHON,
                "handler": "vanna.refresh_training",
                "parameters": {
                    "domain": "default",
                    "full_refresh": False,
                },
                "cron_expression": "0 2 * * 0",
                "timezone": "Asia/Muscat",
                "enabled": False,
                "max_instances": 1,
                "timeout_seconds": 3600,
                "retry_count": 1,
                "retry_delay_seconds": 300,
            },
            {
                "name": "[Sample] Weekday Executive Report",
                "description": (
                    "Template Python job for Excel/PPTX/email reporting. "
                    "Register reports.executive_dashboard before enabling."
                ),
                "job_type": ScheduledJob.JobType.PYTHON,
                "handler": "reports.executive_dashboard",
                "parameters": {
                    "send_email": True,
                    "generate_excel": True,
                    "generate_pptx": True,
                },
                "cron_expression": "30 7 * * 1-5",
                "timezone": "Asia/Muscat",
                "enabled": False,
                "max_instances": 1,
                "timeout_seconds": 1800,
                "retry_count": 2,
                "retry_delay_seconds": 120,
            },
        ]

        created_count = 0
        updated_count = 0
        seeded_jobs = []

        for item in samples:
            name = item.pop("name")
            job, created = ScheduledJob.objects.update_or_create(
                name=name,
                defaults=item,
            )
            seeded_jobs.append(job)

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Created: {job.name}")
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.WARNING(f"Updated: {job.name}")
                )

        if options["with_history"]:
            self._seed_history(seeded_jobs)

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Job Center seed completed. "
                f"Created={created_count}, Updated={updated_count}."
            )
        )
        self.stdout.write(
            "Only '[Sample] GLIS Scheduler Test' is enabled by default."
        )
        self.stdout.write(
            "Review database aliases, SQL, URLs, and registered handlers "
            "before enabling the other sample jobs."
        )

    def _seed_history(self, jobs):
        now = timezone.now()

        status_plan = [
            (
                JobExecution.Status.SUCCESS,
                1,
                "Completed successfully.",
                "",
            ),
            (
                JobExecution.Status.SUCCESS,
                2,
                "Completed successfully.",
                "",
            ),
            (
                JobExecution.Status.FAILED,
                3,
                "",
                "Sample failure: datasource connection unavailable.",
            ),
        ]

        created = 0

        for job in jobs[:3]:
            if job.executions.exists():
                continue

            for status, days_ago, output, error in status_plan:
                started = now - timedelta(days=days_ago, minutes=5)
                finished = started + timedelta(seconds=12 + days_ago)

                JobExecution.objects.create(
                    job=job,
                    status=status,
                    trigger_type=JobExecution.TriggerType.SCHEDULED,
                    attempt=1,
                    started_at=started,
                    finished_at=finished,
                    duration_seconds=(finished - started).total_seconds(),
                    parameters=job.parameters or {},
                    result=(
                        {"success": True, "sample": True}
                        if status == JobExecution.Status.SUCCESS
                        else None
                    ),
                    output=output,
                    error=error,
                    traceback=(
                        "Sample traceback for demonstration only."
                        if status == JobExecution.Status.FAILED
                        else ""
                    ),
                )
                created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created} sample execution-history record(s)."
            )
        )
