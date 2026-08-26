from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orchestrator", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="vannasettings",
            name="provider",
            field=models.CharField(
                choices=[
                    ("demo", "Safe demo adapter"),
                    ("ollama_vanna", "Vanna 2.0 + Ollama (local)"),
                    ("vanna_gateway", "Vanna 2.0 gateway"),
                ],
                default="demo",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="vannasettings",
            name="endpoint",
            field=models.URLField(
                blank=True,
                help_text=(
                    "Ollama host for the local provider (for example "
                    "http://127.0.0.1:11434) or the HTTPS endpoint for a Vanna gateway."
                ),
            ),
        ),
    ]
