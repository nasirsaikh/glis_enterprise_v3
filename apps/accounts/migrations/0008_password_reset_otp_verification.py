from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0007_live_updates_and_password_recovery')]

    operations = [
        migrations.AddField(
            model_name='passwordresetchallenge',
            name='verified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
