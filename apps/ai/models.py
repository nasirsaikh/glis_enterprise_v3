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
