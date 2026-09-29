from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tpa", "0004_inbound_email_creator"),
        ("tickets", "0007_category_allowed_groups"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
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
            model_name="policy",
            name="tpa_organization",
            field=models.ForeignKey(
                blank=True,
                limit_choices_to={"organization_type": "TPA"},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="managed_policies",
                to="tpa.tpaorganization",
            ),
        ),
        migrations.AddField(
            model_name="policy",
            name="initial_enrollment_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="policy",
            name="initial_enrollment_completed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="completed_tpa_policy_enrollments",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="memberaction",
            name="card_number",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="memberaction",
            name="tpa_effective_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="memberaction",
            name="tpa_premium_amount",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=14,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="sourcedocument",
            name="file",
            field=models.FileField(blank=True, upload_to="tpa/sources/%Y/%m/"),
        ),
        migrations.AddField(
            model_name="sourcedocument",
            name="content_type",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="sourcedocument",
            name="size",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="sourcedocument",
            name="processing_state",
            field=models.CharField(
                choices=[
                    ("RECEIVED", "Received"),
                    ("PROCESSING", "Processing"),
                    ("PROCESSED", "Processed"),
                    ("REVIEW", "Needs review"),
                    ("FAILED", "Failed"),
                ],
                db_index=True,
                default="RECEIVED",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="TransactionQuery",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subject", models.CharField(max_length=255)),
                ("pre_query_status", models.CharField(blank=True, max_length=30)),
                (
                    "status",
                    models.CharField(
                        choices=[("OPEN", "Open"), ("RESOLVED", "Resolved")],
                        db_index=True,
                        default="OPEN",
                        max_length=20,
                    ),
                ),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "raised_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="raised_tpa_queries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "resolved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="resolved_tpa_queries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "transaction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="queries",
                        to="tpa.membertransaction",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="TransactionQueryMessage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("QUERY", "Query"),
                            ("REPLY", "Reply"),
                            ("NOTE", "Note"),
                        ],
                        default="REPLY",
                        max_length=12,
                    ),
                ),
                (
                    "query",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="messages",
                        to="tpa.transactionquery",
                    ),
                ),
                (
                    "sender",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="tpa_query_messages",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "ticket_comment",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tpa_query_message",
                        to="tickets.ticketcomment",
                    ),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
    ]
