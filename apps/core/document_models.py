from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .models import TimeStampedModel


class ManagedDocument(TimeStampedModel):
    """GLIS-side index for documents whose authoritative binary is in Mayan EDMS."""

    class Category(models.TextChoices):
        TICKET = "ticket", "Ticket attachment"
        CLAIM = "claim", "Claim document"
        POLICY = "policy", "Policy document"
        LEGAL = "legal", "Legal case document"
        KNOWLEDGE = "knowledge", "Controlled knowledge document"
        GENERAL = "general", "General document"

    mayan_document_id = models.PositiveBigIntegerField(unique=True, db_index=True)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.GENERAL, db_index=True)
    title = models.CharField(max_length=255)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="managed_documents", on_delete=models.SET_NULL)
    content_type_object = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    linked_object = GenericForeignKey("content_type_object", "object_id")
    is_restricted = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    ocr_text = models.TextField(blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("search_all_documents", "Can search all managed documents"),
            ("open_mayan_edms", "Can open the Mayan EDMS administration UI"),
        ]
        indexes = [models.Index(fields=["category", "object_id"])]

    def __str__(self):
        return self.title or self.original_name
