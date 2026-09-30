from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tpa", "0012_merge_workflow_branches"),
    ]

    operations = [
        migrations.AlterField(
            model_name="membertransaction",
            name="transaction_type",
            field=models.CharField(
                choices=[
                    ("NEW_POLICY_ENROLLMENT", "New Policy Enrollment"),
                    ("MEMBER_ADD", "Member Addition"),
                    ("MEMBER_UPDATE", "Member Demographic Change"),
                    ("MEMBER_TERMINATE", "Member Termination"),
                    ("MEMBER_SUSPEND", "Temporary Suspension"),
                    ("MEMBER_REACTIVATE", "Member Reactivation"),
                    ("MEMBER_DELETE", "Member Deletion / Void"),
                    ("POLICY_CANCEL", "Policy Cancellation"),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
    ]
