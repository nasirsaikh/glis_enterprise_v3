from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tpa", "0002_document_email_intake"),
    ]

    operations = [
        migrations.AddField(
            model_name="inboundemail",
            name="processing_hints",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="inboundemail",
            name="ai_extracted_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="inboundemail",
            name="ai_confidence",
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=5, null=True
            ),
        ),
        migrations.AddField(
            model_name="inboundemail",
            name="processed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="InboundEmailAttachment",
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
                    "file",
                    models.FileField(upload_to="tpa/inbound/%Y/%m/"),
                ),
                ("original_name", models.CharField(max_length=255)),
                ("content_type", models.CharField(blank=True, max_length=120)),
                ("size", models.PositiveIntegerField(default=0)),
                ("sha256", models.CharField(db_index=True, max_length=64)),
                (
                    "processing_state",
                    models.CharField(
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
                ("extracted_payload", models.JSONField(blank=True, default=dict)),
                ("processing_error", models.TextField(blank=True)),
                (
                    "inbound_email",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="tpa.inboundemail",
                    ),
                ),
            ],
        ),
    ]
