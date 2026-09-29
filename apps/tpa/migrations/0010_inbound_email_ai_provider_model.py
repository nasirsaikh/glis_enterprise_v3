from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tpa", "0009_merge_automated_endorsement_branches"),
    ]

    operations = [
        migrations.AddField(
            model_name="inboundemail",
            name="ai_provider_name",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="inboundemail",
            name="ai_model_name",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
