from django.db import migrations, models
from django.db.models import Q


def backfill_profile_organizations(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    TPAOrganization = apps.get_model("tpa", "TPAOrganization")
    for profile in UserProfile.objects.exclude(organization="").iterator():
        value = (profile.organization or "").strip()
        if not value:
            continue
        organization = TPAOrganization.objects.filter(
            Q(code__iexact=value)
            | Q(name_en__iexact=value)
            | Q(name_ar__iexact=value)
        ).first()
        if organization:
            profile.organizations.add(organization)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_userprofile_daisyui_themes"),
        ("tpa", "0014_merge_20260930_1202"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="organizations",
            field=models.ManyToManyField(
                blank=True,
                help_text="Organizations this user may act for across portal workflows.",
                related_name="user_profiles",
                to="tpa.tpaorganization",
            ),
        ),
        migrations.RunPython(
            backfill_profile_organizations,
            migrations.RunPython.noop,
        ),
    ]
