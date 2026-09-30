import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_alter_sitesettings_hero_eyebrow_ar_and_more"),
        ("tpa", "0014_merge_20260930_1202"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="default_tpa_organization",
            field=models.ForeignKey(
                blank=True,
                help_text="Default TPA used for new policy enrollments. Configure this once at site level.",
                limit_choices_to={"organization_type": "TPA", "is_active": True},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="tpa.tpaorganization",
            ),
        ),
    ]
