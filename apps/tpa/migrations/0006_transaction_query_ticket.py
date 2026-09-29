from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tpa", "0005_smartendorse_workflow"),
        ("tickets", "0007_category_allowed_groups"),
    ]

    operations = [
        migrations.AddField(
            model_name="transactionquery",
            name="ticket",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tpa_query",
                to="tickets.ticket",
            ),
        ),
    ]
