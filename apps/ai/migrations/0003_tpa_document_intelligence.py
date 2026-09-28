from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies=[("ai","0002_initial")]
    operations=[
        migrations.CreateModel(
            name="AIProviderConfig",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
                ("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
                ("name",models.CharField(max_length=120,unique=True)),
                ("provider",models.CharField(choices=[("mock","Mock / Testing"),("ollama","Ollama"),("openai_compatible","OpenAI-compatible"),("openai","OpenAI"),("anthropic","Anthropic")],default="mock",max_length=30)),
                ("model_name",models.CharField(blank=True,max_length=120)),("endpoint",models.URLField(blank=True)),
                ("secret_reference",models.CharField(blank=True,help_text="Environment/secret-manager reference; never store API keys here.",max_length=160)),
                ("temperature",models.DecimalField(decimal_places=2,default=0,max_digits=3)),("timeout_seconds",models.PositiveIntegerField(default=120)),
                ("supports_vision",models.BooleanField(default=False)),("task_capabilities",models.JSONField(blank=True,default=list)),("runtime_options",models.JSONField(blank=True,default=dict)),
                ("allow_sensitive_data",models.BooleanField(default=False)),("is_active",models.BooleanField(default=True)),("priority",models.PositiveSmallIntegerField(default=100)),
            ],
        ),
        migrations.CreateModel(
            name="AIExtractionProfile",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
                ("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
                ("name",models.CharField(max_length=140)),
                ("task",models.CharField(choices=[("DOCUMENT_EXTRACTION","Document extraction"),("STRUCTURED_HEADER_MAPPING","Structured header mapping"),("MEMBER_FIELD_MAPPING","Member field mapping"),("EMAIL_EXTRACTION","Email extraction"),("DOCUMENT_CLASSIFICATION","Document classification")],db_index=True,max_length=40)),
                ("applicable_product",models.CharField(blank=True,max_length=80)),("applicable_transaction_type",models.CharField(blank=True,max_length=40)),
                ("system_prompt",models.TextField(blank=True)),("instructions",models.TextField(blank=True)),("field_aliases",models.JSONField(blank=True,default=dict)),
                ("priority",models.PositiveSmallIntegerField(default=100)),("is_active",models.BooleanField(default=True)),
            ],
            options={"ordering":("priority","name")},
        ),
        migrations.CreateModel(
            name="AITrainingExample",
            fields=[
                ("id",models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name="ID")),
                ("created_at",models.DateTimeField(auto_now_add=True)),("updated_at",models.DateTimeField(auto_now=True)),
                ("name",models.CharField(max_length=140)),("input_text",models.TextField()),("expected_output",models.JSONField(default=dict)),
                ("sort_order",models.PositiveSmallIntegerField(default=0)),("is_active",models.BooleanField(default=True)),
                ("profile",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="examples",to="ai.aiextractionprofile")),
            ],
            options={"ordering":("sort_order","id")},
        ),
    ]
