from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from apps.core.models import TimeStampedModel


class UserProfile(TimeStampedModel):
    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        ADMIN = "admin", "Admin"
        PROJECT_MANAGER = "project_manager", "Project Manager"
        SUPPORT_AGENT = "support_agent", "Support Agent"
        REQUESTER = "requester", "Requester/User"
        VIEWER = "viewer", "Viewer/Auditor"
        GUEST = "guest", "Guest"

    class SidebarMode(models.TextChoices):
        FULL = "full", "Full navigation"
        MINI = "mini", "Icon-only navigation"
        HIDDEN = "hidden", "Hidden navigation"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.GUEST, db_index=True)
    phone = models.CharField(max_length=30, blank=True)
    organization = models.CharField(max_length=150, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    department = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to="profiles/%Y/%m/", blank=True)
    reporting_manager = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="direct_reports", on_delete=models.SET_NULL)
    preferred_language = models.CharField(max_length=5, default="en", choices=[("en", "English"), ("ar", "العربية")])
    theme = models.CharField(max_length=10, default="system", choices=[("system", "System"), ("light", "Light"), ("dark", "Dark")])
    sidebar_mode = models.CharField(max_length=10, choices=SidebarMode.choices, default=SidebarMode.MINI)
    is_external = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=True)
    guest_access_expires_at = models.DateTimeField(null=True, blank=True)
    email_notifications = models.BooleanField(default=True)
    browser_notifications = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.user} · {self.get_role_display()}"


class AccountPolicy(TimeStampedModel):
    public_registration_enabled = models.BooleanField(default=True)
    google_login_enabled = models.BooleanField(default=True)
    microsoft_login_enabled = models.BooleanField(default=True)
    default_external_role = models.CharField(max_length=30, choices=UserProfile.Role.choices, default=UserProfile.Role.GUEST)
    default_external_group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL)
    allowed_email_domains = models.JSONField(default=list, blank=True)
    external_users_require_approval = models.BooleanField(default=False)
    guest_ticket_visibility = models.CharField(max_length=20, default="own", choices=[("own", "Own only"), ("own_group", "Own and allowed group")])

    class Meta:
        verbose_name_plural = "Account policies"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
