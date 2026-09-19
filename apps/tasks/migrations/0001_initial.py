import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_task_generator_job(apps, schema_editor):
    ScheduledJob = apps.get_model("job_center", "ScheduledJob")
    ScheduledJob.objects.update_or_create(
        name="Recurring task generator",
        defaults={
            "description": "Creates GLIS task occurrences and linked tickets when their configured create-ahead date is reached.",
            "job_type": "PYTHON",
            "handler": "tasks.generate_due",
            "parameters": {},
            "cron_expression": "5 0 * * *",
            "timezone": "Asia/Muscat",
            "enabled": True,
            "max_instances": 1,
            "timeout_seconds": 900,
            "retry_count": 1,
            "retry_delay_seconds": 60,
            "misfire_grace_seconds": 3600,
            "coalesce": True,
        },
    )


def remove_task_generator_job(apps, schema_editor):
    ScheduledJob = apps.get_model("job_center", "ScheduledJob")
    ScheduledJob.objects.filter(name="Recurring task generator").delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tickets", "0007_category_allowed_groups"),
        ("job_center", "0002_queuedjob"),
    ]

    operations = [
        migrations.CreateModel(
            name="RecurringTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=240)),
                ("description", models.TextField(blank=True)),
                ("priority", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")], default="medium", max_length=15)),
                ("first_due_date", models.DateField(help_text="The first due date in the recurrence pattern.")),
                ("recurrence", models.CharField(choices=[("daily", "Daily"), ("weekly", "Weekly"), ("fortnightly", "Fortnightly"), ("monthly", "Monthly"), ("quarterly", "Quarterly"), ("half_yearly", "Half yearly"), ("yearly", "Yearly"), ("one_time", "One time")], default="monthly", max_length=20)),
                ("create_days_before", models.PositiveSmallIntegerField(default=0, help_text="Create each task and its ticket this many calendar days before the due date.")),
                ("is_active", models.BooleanField(default=True)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recurring_tasks", to="tickets.category")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_recurring_tasks", to=settings.AUTH_USER_MODEL)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="owned_recurring_tasks", to=settings.AUTH_USER_MODEL)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recurring_tasks", to="tickets.product")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recurring_tasks", to="tickets.project")),
                ("tagged_users", models.ManyToManyField(blank=True, related_name="tagged_recurring_tasks", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_recurring_tasks", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("title", "first_due_date"),
                "permissions": [("manage_recurring_tasks", "Can manage recurring tasks")],
            },
        ),
        migrations.CreateModel(
            name="Task",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("occurrence_date", models.DateField(help_text="Scheduled recurrence date used for duplicate prevention.")),
                ("due_date", models.DateField(db_index=True)),
                ("title", models.CharField(max_length=240)),
                ("description", models.TextField(blank=True)),
                ("priority", models.CharField(choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")], default="medium", max_length=15)),
                ("is_deleted", models.BooleanField(db_index=True, default=False)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tasks", to="tickets.category")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_tasks", to=settings.AUTH_USER_MODEL)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="owned_tasks", to=settings.AUTH_USER_MODEL)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tasks", to="tickets.product")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="tasks", to="tickets.project")),
                ("recurring_task", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="generated_tasks", to="tasks.recurringtask")),
                ("tagged_users", models.ManyToManyField(blank=True, related_name="tagged_tasks", to=settings.AUTH_USER_MODEL)),
                ("ticket", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="task_item", to="tickets.ticket")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_tasks", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("due_date", "title"),
                "permissions": [("manage_tasks", "Can manage tasks")],
            },
        ),
        migrations.AddConstraint(
            model_name="task",
            constraint=models.UniqueConstraint(
                condition=models.Q(recurring_task__isnull=False),
                fields=("recurring_task", "occurrence_date"),
                name="unique_recurring_task_occurrence",
            ),
        ),
        migrations.RunPython(seed_task_generator_job, remove_task_generator_job),
    ]
