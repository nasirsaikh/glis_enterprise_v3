from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tpa", "0006_transaction_query_ticket"),
    ]

    operations = [
        migrations.AddField(
            model_name="memberpolicyenrollment",
            name="card_number",
            field=models.CharField(blank=True, max_length=100),
        ),
    ]
