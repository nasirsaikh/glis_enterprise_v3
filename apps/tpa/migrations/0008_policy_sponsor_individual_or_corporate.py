from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("tpa", "0007_enrollment_card_number"),
    ]

    operations = [
        migrations.AlterField(
            model_name="policy",
            name="sponsor",
            field=models.ForeignKey(
                limit_choices_to={
                    "organization_type__in": ["INDIVIDUAL", "CORPORATE"]
                },
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sponsored_policies",
                to="tpa.tpaorganization",
            ),
        ),
    ]
