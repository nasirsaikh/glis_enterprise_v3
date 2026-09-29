from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tpa", "0010_inbound_email_ai_provider_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="membertransaction",
            name="expected_reactivation_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
