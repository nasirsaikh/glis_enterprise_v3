from django.conf import settings
from django.db import models
from django.utils.translation import get_language


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class LocalizedModelMixin:
    def localized(self, field: str) -> str:
        language = (get_language() or "en").split("-")[0]
        value = getattr(self, f"{field}_{language}", "")
        return value or getattr(self, f"{field}_en", "")


class ModuleRegistry(TimeStampedModel, LocalizedModelMixin):
    key = models.SlugField(unique=True)
    name_en = models.CharField(max_length=120)
    name_ar = models.CharField(max_length=120, blank=True)
    description_en = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    icon = models.CharField(max_length=50, default="bi-grid")
    route_name = models.CharField(max_length=120, blank=True)
    is_enabled = models.BooleanField(default=True)
    show_in_navigation = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)
    required_permission = models.CharField(max_length=150, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["order", "name_en"]
        permissions = [("manage_modules", "Can manage module registry")]

    def __str__(self):
        return self.name_en


class ConfigurationVersion(TimeStampedModel):
    key = models.CharField(max_length=120)
    version = models.PositiveIntegerField()
    state = models.CharField(max_length=20, choices=[("draft", "Draft"), ("published", "Published"), ("archived", "Archived")])
    payload = models.JSONField(default=dict)
    validation_errors = models.JSONField(default=list, blank=True)
    change_note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-version"]
        constraints = [models.UniqueConstraint(fields=["key", "version"], name="unique_configuration_version")]
        permissions = [("manage_json_config", "Can manage JSON configuration")]


class AuditLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80, db_index=True)
    object_type = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    summary = models.CharField(max_length=255)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    sensitivity = models.CharField(max_length=20, default="normal", choices=[("normal", "Normal"), ("sensitive", "Sensitive"), ("security", "Security")])

    class Meta:
        ordering = ["-created_at"]
        permissions = [("view_audit", "Can view audit logs")]

    @classmethod
    def record(cls, *, request=None, actor=None, action, instance=None, summary, changes=None, sensitivity="normal"):
        if request:
            actor = actor or (request.user if request.user.is_authenticated else None)
        return cls.objects.create(
            actor=actor, action=action,
            object_type=instance._meta.label if instance else "",
            object_id=str(instance.pk) if instance and instance.pk else "",
            summary=summary, changes=changes or {}, sensitivity=sensitivity,
            ip_address=(request.META.get("REMOTE_ADDR") if request else None),
            user_agent=(request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""),
        )
