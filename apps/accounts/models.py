from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.core.exceptions import ValidationError
from apps.core.models import TimeStampedModel


class OrganizationType(TimeStampedModel):
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=80, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('display_order', 'name')

    def __str__(self):
        return self.name


class Organization(TimeStampedModel):
    # Compatibility constants identify seeded masters; the FK allows new types.
    class Type:
        INDIVIDUAL = 'INDIVIDUAL'
        CORPORATE = 'CORPORATE'
        INSURER = 'INSURER'
        TPA = 'TPA'
        BROKER = 'BROKER'
        AGENT = 'AGENT'
        OTHER = 'OTHER'

    code = models.CharField(max_length=40, unique=True)
    name_en = models.CharField(max_length=180)
    name_ar = models.CharField(max_length=180, blank=True)
    organization_type = models.ForeignKey(OrganizationType, to_field='code', on_delete=models.PROTECT, related_name='organizations')
    parent_organization = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='children')
    commercial_registration = models.CharField(max_length=80, blank=True)
    tax_number = models.CharField(max_length=80, blank=True)
    contact_name = models.CharField(max_length=160, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=60, blank=True)
    address = models.TextField(blank=True)
    country = models.CharField(max_length=80, blank=True)
    configuration = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def clean(self):
        seen = {self.pk} if self.pk else set()
        parent = self.parent_organization
        while parent:
            if parent.pk in seen:
                raise ValidationError({'parent_organization': 'Organization hierarchy cannot contain a cycle.'})
            seen.add(parent.pk)
            parent = parent.parent_organization

    def get_organization_type_display(self):
        return self.organization_type.name

    def __str__(self):
        return f'{self.code} · {self.name_en}'


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
    # Legacy free-text value retained for backwards compatibility. New access
    # control and workflow routing use the global organizations M2M below.
    organization = models.CharField(max_length=150, blank=True)
    organizations = models.ManyToManyField(
        "accounts.Organization",
        related_name="user_profiles",
        blank=True,
        help_text="Organizations this user may act for across portal workflows.",
    )
    job_title = models.CharField(max_length=120, blank=True)
    department = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)
    avatar = models.ImageField(upload_to="profiles/%Y/%m/", blank=True)
    reporting_manager = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="direct_reports", on_delete=models.SET_NULL)
    preferred_language = models.CharField(max_length=5, default="en", choices=[("en", "English"), ("ar", "العربية")])
    THEME_CHOICES = [
        ("system", "System"),
        ("light", "Light"),
        ("dark", "Dark"),
        ("cupcake", "Cupcake"),
        ("bumblebee", "Bumblebee"),
        ("emerald", "Emerald"),
        ("corporate", "Corporate"),
        ("synthwave", "Synthwave"),
        ("retro", "Retro"),
        ("cyberpunk", "Cyberpunk"),
        ("valentine", "Valentine"),
        ("halloween", "Halloween"),
        ("garden", "Garden"),
        ("forest", "Forest"),
        ("aqua", "Aqua"),
        ("lofi", "Lo-fi"),
        ("pastel", "Pastel"),
        ("fantasy", "Fantasy"),
        ("wireframe", "Wireframe"),
        ("black", "Black"),
        ("luxury", "Luxury"),
        ("dracula", "Dracula"),
        ("cmyk", "CMYK"),
        ("autumn", "Autumn"),
        ("business", "Business"),
        ("acid", "Acid"),
        ("lemonade", "Lemonade"),
        ("night", "Night"),
        ("coffee", "Coffee"),
        ("winter", "Winter"),
        ("dim", "Dim"),
        ("nord", "Nord"),
        ("sunset", "Sunset"),
        ("caramellatte", "Caramellatte"),
        ("abyss", "Abyss"),
        ("silk", "Silk"),
    ]
    theme = models.CharField(max_length=20, default="system", choices=THEME_CHOICES)
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
