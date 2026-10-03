from django.conf import settings
from django.db import models
from apps.core.models import TimeStampedModel


class AISettings(TimeStampedModel):
    provider = models.CharField(max_length=30, default="mock", choices=[("mock", "Mock"), ("openai_compatible", "OpenAI-compatible")])
    endpoint = models.URLField(blank=True)
    model_name = models.CharField(max_length=100, blank=True)
    system_prompt = models.TextField(default="Assist with insurance service requests. Never make final coverage or claim decisions.")
    timeout_seconds = models.PositiveSmallIntegerField(default=30)
    intake_questions = models.JSONField(default=list, blank=True)
    enable_category_suggestion = models.BooleanField(default=True)
    enable_priority_suggestion = models.BooleanField(default=True)
    enable_group_suggestion = models.BooleanField(default=True)
    enable_assignee_suggestion = models.BooleanField(default=False)
    enable_similar_tickets = models.BooleanField(default=True)
    enable_knowledge_suggestion = models.BooleanField(default=True)
    confidence_threshold = models.DecimalField(max_digits=4, decimal_places=3, default=0.650)
    allow_sensitive_fields = models.BooleanField(default=False)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "AI settings"
        permissions = [("configure_ai", "Can configure AI")]

    def save(self, *args, **kwargs):
        self.pk = 1
        if len(self.intake_questions) != 4:
            self.intake_questions = default_questions()
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"intake_questions": default_questions()})
        return obj


def default_questions():
    return [
        {"text": "What outcome are you expecting?", "optional": False, "chips": ["Information", "Correction", "Resolution"]},
        {"text": "When did this issue or request begin?", "optional": False, "chips": ["Today", "This week", "Earlier"]},
        {"text": "Who is affected by this issue?", "optional": False, "chips": ["Only me", "A member", "Several people"]},
        {"text": "What troubleshooting or actions have already been attempted?", "optional": True, "chips": ["None yet", "Called support", "Shared documents"]},
    ]


class AIInteraction(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    ticket = models.ForeignKey("tickets.Ticket", null=True, blank=True, on_delete=models.SET_NULL)
    purpose = models.CharField(max_length=50)
    provider = models.CharField(max_length=50)
    request_summary = models.JSONField(default=dict)
    response = models.JSONField(default=dict)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True)
    duration_ms = models.PositiveIntegerField(default=0)
    succeeded = models.BooleanField(default=True)
    error_code = models.CharField(max_length=50, blank=True)


class AIProviderConfig(TimeStampedModel):
    class Provider(models.TextChoices):
        MOCK="mock","Mock / Testing"
        OLLAMA="ollama","Ollama"
        HUGGINGFACE="huggingface","Hugging Face"
        OPENAI_COMPATIBLE="openai_compatible","OpenAI-compatible"
        OPENAI="openai","OpenAI"
        ANTHROPIC="anthropic","Anthropic"
    name=models.CharField(max_length=120, unique=True)
    provider=models.CharField(max_length=30, choices=Provider.choices, default=Provider.MOCK)
    model_name=models.CharField(max_length=120, blank=True)
    endpoint=models.URLField(blank=True)
    secret_reference=models.CharField(max_length=160, blank=True, help_text="Environment/secret-manager reference; never store API keys here.")
    temperature=models.DecimalField(max_digits=3, decimal_places=2, default=0)
    timeout_seconds=models.PositiveIntegerField(default=120)
    supports_vision=models.BooleanField(default=False)
    task_capabilities=models.JSONField(default=list, blank=True)
    runtime_options=models.JSONField(default=dict, blank=True)
    allow_sensitive_data=models.BooleanField(default=False)
    is_active=models.BooleanField(default=True)
    priority=models.PositiveSmallIntegerField(default=100)
    def __str__(self): return f"{self.name} · {self.model_name or self.provider}"

class AIExtractionProfile(TimeStampedModel):
    class Task(models.TextChoices):
        DOCUMENT_EXTRACTION="DOCUMENT_EXTRACTION","Document extraction"
        STRUCTURED_HEADER_MAPPING="STRUCTURED_HEADER_MAPPING","Structured header mapping"
        MEMBER_FIELD_MAPPING="MEMBER_FIELD_MAPPING","Member field mapping"
        EMAIL_EXTRACTION="EMAIL_EXTRACTION","Email extraction"
        DOCUMENT_CLASSIFICATION="DOCUMENT_CLASSIFICATION","Document classification"
    name=models.CharField(max_length=140)
    task=models.CharField(max_length=40, choices=Task.choices, db_index=True)
    applicable_product=models.CharField(max_length=80, blank=True)
    applicable_transaction_type=models.CharField(max_length=40, blank=True)
    system_prompt=models.TextField(blank=True)
    instructions=models.TextField(blank=True)
    field_aliases=models.JSONField(default=dict, blank=True)
    priority=models.PositiveSmallIntegerField(default=100)
    is_active=models.BooleanField(default=True)
    class Meta: ordering=("priority","name")
    def __str__(self): return f"{self.get_task_display()} · {self.name}"

class AITrainingExample(TimeStampedModel):
    profile=models.ForeignKey(AIExtractionProfile, related_name="examples", on_delete=models.CASCADE)
    name=models.CharField(max_length=140)
    input_text=models.TextField()
    expected_output=models.JSONField(default=dict)
    sort_order=models.PositiveSmallIntegerField(default=0)
    is_active=models.BooleanField(default=True)
    class Meta: ordering=("sort_order","id")
    def __str__(self): return self.name
