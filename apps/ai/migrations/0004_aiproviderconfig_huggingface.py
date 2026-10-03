from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0003_tpa_document_intelligence"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aiproviderconfig",
            name="provider",
            field=models.CharField(
                choices=[
                    ("mock", "Mock / Testing"),
                    ("ollama", "Ollama"),
                    ("huggingface", "Hugging Face"),
                    ("openai_compatible", "OpenAI-compatible"),
                    ("openai", "OpenAI"),
                    ("anthropic", "Anthropic"),
                ],
                default="mock",
                max_length=30,
            ),
        ),
    ]
