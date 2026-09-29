from django.db import migrations, models


def seed_office365_sync_job(apps, schema_editor):
    ScheduledJob = apps.get_model("job_center", "ScheduledJob")
    ScheduledJob.objects.update_or_create(
        name="TPA Office365 Mailbox Sync",
        defaults={
            "description": (
                "Automatically synchronize the configured TPA Office365/shared mailbox "
                "through Microsoft Graph and process new endorsement requests."
            ),
            "job_type": "PYTHON",
            "handler": "tpa.poll_inbound_mailbox",
            "parameters": {},
            "cron_expression": "*/5 * * * *",
            "timezone": "Asia/Muscat",
            "enabled": True,
            "max_instances": 1,
            "timeout_seconds": 300,
            "retry_count": 2,
            "retry_delay_seconds": 60,
            "misfire_grace_seconds": 300,
            "coalesce": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("job_center", "0001_initial"),
        ("tpa", "0007_automated_endorsement_operations"),
    ]

    operations = [
        migrations.AlterField(
            model_name="membertransaction",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("extracting", "Extracting"),
                    ("pending_validation", "Pending Validation"),
                    ("needs_information", "Needs Information"),
                    ("validation_failed", "Validation Failed"),
                    ("pending_approval", "Pending Approval"),
                    ("approved", "Approved"),
                    ("auto_approved", "Auto Approved"),
                    ("sent_to_tpa", "Sent to TPA"),
                    ("tpa_in_progress", "TPA In Progress"),
                    ("tpa_query", "TPA Query"),
                    ("card_dispatch", "Card Dispatch"),
                    ("processing", "Processing"),
                    ("processed", "Processed"),
                    ("completed", "Completed"),
                    ("rejected", "Rejected"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                db_index=True,
                default="draft",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="memberaction",
            name="tpa_override_reason",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(seed_office365_sync_job, migrations.RunPython.noop),
    ]
