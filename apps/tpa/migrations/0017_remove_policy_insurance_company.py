from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tpa", "0016_unified_workflow_backfill"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="policy",
            name="insurance_company",
        ),
    ]
