from django.db import migrations, models


def backfill_support_group_organizations(apps, schema_editor):
    SupportGroup = apps.get_model("tickets", "SupportGroup")
    UserProfile = apps.get_model("accounts", "UserProfile")
    for group in SupportGroup.objects.prefetch_related("members", "managers").iterator():
        user_ids = list(group.members.values_list("pk", flat=True))
        user_ids.extend(group.managers.values_list("pk", flat=True))
        organization_ids = (
            UserProfile.objects.filter(user_id__in=set(user_ids))
            .values_list("organizations__pk", flat=True)
            .exclude(organizations__pk__isnull=True)
            .distinct()
        )
        group.organizations.add(*organization_ids)


class Migration(migrations.Migration):

    dependencies = [
        ("tickets", "0007_category_allowed_groups"),
        ("accounts", "0005_userprofile_organizations"),
        ("tpa", "0014_merge_20260930_1202"),
    ]

    operations = [
        migrations.AddField(
            model_name="supportgroup",
            name="organizations",
            field=models.ManyToManyField(
                blank=True,
                help_text="Organizations whose users may use this support group for ticket routing and reassignment.",
                related_name="support_groups",
                to="tpa.tpaorganization",
            ),
        ),
        migrations.RunPython(
            backfill_support_group_organizations,
            migrations.RunPython.noop,
        ),
    ]
