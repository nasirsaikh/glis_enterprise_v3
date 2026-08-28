from pathlib import Path
import uuid
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from apps.core.models import LocalizedModelMixin, TimeStampedModel


def validate_attachment(file):
    allowed = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".xls", ".xlsx"}
    if Path(file.name).suffix.lower() not in allowed:
        raise ValidationError("Unsupported attachment type.")
    if file.size > 10 * 1024 * 1024:
        raise ValidationError("Attachment exceeds the 10 MB limit.")


class SupportGroup(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    code = models.SlugField(unique=True)
    auth_group = models.OneToOneField(Group, null=True, blank=True, on_delete=models.SET_NULL)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="support_groups", blank=True)
    managers = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="managed_support_groups", blank=True)
    description = models.TextField(blank=True)
    can_view_all_group_tickets = models.BooleanField(default=True)
    can_edit_group_tickets = models.BooleanField(default=True)
    can_assign_group_tickets = models.BooleanField(default=False)
    can_view_sensitive = models.BooleanField(default=False)
    can_view_internal_notes = models.BooleanField(default=True)
    can_view_restricted_attachments = models.BooleanField(default=False)
    can_access_reports = models.BooleanField(default=False)
    routing_config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Project(TimeStampedModel, LocalizedModelMixin):
    code = models.CharField(max_length=20, unique=True)
    name_en = models.CharField(max_length=140)
    name_ar = models.CharField(max_length=140, blank=True)
    description_en = models.TextField(blank=True)
    description_ar = models.TextField(blank=True)
    groups = models.ManyToManyField(SupportGroup, related_name="projects", blank=True)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="ticket_projects", blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        permissions = [("manage_projects", "Can manage projects")]

    def __str__(self):
        return f"{self.code} · {self.name_en}"


class Product(TimeStampedModel, LocalizedModelMixin):
    project = models.ForeignKey(Project, related_name="products", on_delete=models.CASCADE)
    code = models.CharField(max_length=30)
    name_en = models.CharField(max_length=140)
    name_ar = models.CharField(max_length=140, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "code"], name="unique_project_product")]
        permissions = [("manage_products", "Can manage products")]

    def __str__(self):
        return self.name_en


class Category(TimeStampedModel, LocalizedModelMixin):
    product = models.ForeignKey(Product, related_name="categories", on_delete=models.CASCADE)
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.CASCADE)
    code = models.CharField(max_length=30)
    name_en = models.CharField(max_length=140)
    name_ar = models.CharField(max_length=140, blank=True)
    default_priority = models.CharField(max_length=15, default="medium", choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")])
    default_group = models.ForeignKey(SupportGroup, null=True, blank=True, on_delete=models.SET_NULL)
    default_groups = models.ManyToManyField(SupportGroup, related_name="default_for_categories", blank=True)
    default_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="default_categories", on_delete=models.SET_NULL)
    ai_enabled = models.BooleanField(default=True)
    required_documents = models.JSONField(default=list, blank=True, help_text="Admin-driven attachment definitions used by the ticket form.")
    comment_attachment_required = models.BooleanField(default=False,help_text="Enable and require attachments when posting comments for this category.",)
    comment_attachment_max_size_mb = models.PositiveIntegerField(default=5,help_text=("Maximum size in MB for each file uploaded ""with a ticket comment."),)    
    comment_attachment_max_count = models.PositiveIntegerField(default=5,help_text=("Maximum number of files allowed per comment."),)
    comment_attachment_extensions = models.CharField(max_length=500,default="pdf,jpg,jpeg,png,doc,docx,xls,xlsx",help_text=("Comma-separated allowed file extensions. ""Example: pdf,jpg,jpeg,png,doc,docx,xls,xlsx"),)
    auto_close_days = models.PositiveSmallIntegerField(default=7)
    reopen_allowed_days = models.PositiveSmallIntegerField(default=14)
    send_initial_email = models.BooleanField(default=True)
    send_update_email = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    @property
    def comment_attachment_extensions_list(self):
        return [f".{extension.strip().lower().lstrip('.')}" for extension in self.comment_attachment_extensions.split(",") if extension.strip()]
    class Meta:
        verbose_name_plural = "Categories"
        constraints = [
            models.UniqueConstraint(fields=["product", "code"],name="unique_product_category",)]
        permissions = [("manage_categories","Can manage categories",)]
    def __str__(self):
        return self.name_en

def default_pause_statuses():
    return ["pending_customer"]


class SLAPolicy(TimeStampedModel):
    name = models.CharField(max_length=120)
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.CASCADE)
    priority = models.CharField(max_length=15, default="medium", choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")])
    first_response_minutes = models.PositiveIntegerField(default=240)
    resolution_minutes = models.PositiveIntegerField(default=1440)
    pause_statuses = models.JSONField(default=default_pause_statuses, blank=True)
    business_calendar = models.JSONField(default=dict, blank=True)
    escalation_rules = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        permissions = [("manage_sla", "Can manage SLA policies")]

    def __str__(self):
        return self.name


class SLAEscalationRule(TimeStampedModel):
    policy = models.ForeignKey(SLAPolicy, related_name="escalation_levels", on_delete=models.CASCADE)
    level = models.PositiveSmallIntegerField(default=1)
    trigger_after_minutes = models.PositiveIntegerField(help_text="Minutes after the relevant SLA due time.")
    target_users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="sla_escalation_rules", blank=True)
    target_groups = models.ManyToManyField(SupportGroup, related_name="sla_escalation_rules", blank=True)
    include_assignee_reporting_manager = models.BooleanField(default=False)
    notification_message = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("policy", "level")
        constraints = [models.UniqueConstraint(fields=["policy", "level"], name="unique_sla_policy_level")]

    def __str__(self):
        return f"{self.policy} · Level {self.level}"


class ApprovalWorkflow(TimeStampedModel):
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ApprovalStep(TimeStampedModel):
    workflow = models.ForeignKey(ApprovalWorkflow, related_name="steps", on_delete=models.CASCADE)
    sequence = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=160)
    approver_users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="ticket_approval_steps", blank=True)
    approver_groups = models.ManyToManyField(SupportGroup, related_name="ticket_approval_steps", blank=True)
    approvals_required = models.PositiveSmallIntegerField(default=1)
    escalation_after_hours = models.PositiveSmallIntegerField(default=24)
    rejection_ends_workflow = models.BooleanField(default=True)

    class Meta:
        ordering = ("workflow", "sequence")
        constraints = [models.UniqueConstraint(fields=["workflow", "sequence"], name="unique_approval_workflow_sequence")]

    def __str__(self):
        return f"{self.workflow} · {self.sequence}. {self.name}"


Category.add_to_class("approval_workflow", models.ForeignKey(ApprovalWorkflow, null=True, blank=True, related_name="categories", on_delete=models.SET_NULL))


class DynamicForm(TimeStampedModel, LocalizedModelMixin):
    key = models.SlugField(unique=True)
    name_en = models.CharField(max_length=160)
    name_ar = models.CharField(max_length=160, blank=True)
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL)
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL)
    category = models.ForeignKey(Category, null=True, blank=True, related_name="dynamic_forms", on_delete=models.SET_NULL)
    active_version = models.ForeignKey("DynamicFormVersion", null=True, blank=True, related_name="active_for_forms", on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)

    class Meta:
        permissions = [("manage_forms", "Can manage dynamic forms"), ("publish_forms", "Can publish dynamic forms")]

    def __str__(self):
        return self.name_en


class DynamicFormVersion(TimeStampedModel):
    form = models.ForeignKey(DynamicForm, related_name="versions", on_delete=models.CASCADE)
    version = models.PositiveIntegerField()
    state = models.CharField(max_length=20, default="draft", choices=[("draft", "Draft"), ("published", "Published"), ("archived", "Archived")])
    schema = models.JSONField(default=dict)
    validation_errors = models.JSONField(default=list, blank=True)
    change_note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-version"]
        constraints = [models.UniqueConstraint(fields=["form", "version"], name="unique_dynamic_form_version")]


class DynamicFieldSchema(TimeStampedModel):
    form_version = models.ForeignKey(DynamicFormVersion, related_name="field_rows", on_delete=models.CASCADE)
    name = models.SlugField()
    label_en = models.CharField(max_length=160)
    label_ar = models.CharField(max_length=160, blank=True)
    control = models.CharField(max_length=30)
    required = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)
    configuration = models.JSONField(default=dict)

    class Meta:
        ordering = ["order"]
        constraints = [models.UniqueConstraint(fields=["form_version", "name"], name="unique_version_field")]


class FormDataSource(TimeStampedModel):
    key = models.SlugField(unique=True)
    label = models.CharField(max_length=120)
    handler = models.CharField(max_length=120, help_text="Allowlisted registry handler key; never raw SQL.")
    metadata = models.JSONField(default=dict, blank=True)
    allowed_roles = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)


class Ticket(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "new", "New"
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In Progress"
        PENDING_CUSTOMER = "pending_customer", "Pending Customer"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    reference = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    subject = models.CharField(max_length=240)
    description = models.TextField()
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="requested_tickets", on_delete=models.PROTECT)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="assigned_tickets", on_delete=models.SET_NULL)
    assignees = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="multi_assigned_tickets", blank=True)
    project = models.ForeignKey(Project, related_name="tickets", on_delete=models.PROTECT)
    product = models.ForeignKey(Product, related_name="tickets", on_delete=models.PROTECT)
    category = models.ForeignKey(Category, related_name="tickets", on_delete=models.PROTECT)
    groups = models.ManyToManyField(SupportGroup, related_name="tickets", blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.NEW, db_index=True)
    priority = models.CharField(max_length=15, choices=Priority.choices, default=Priority.MEDIUM, db_index=True)
    visibility = models.CharField(max_length=20, default="standard", choices=[("standard", "Standard"), ("restricted", "Restricted")])
    is_sensitive = models.BooleanField(default=False)
    tags = models.JSONField(default=list, blank=True)
    sla_policy = models.ForeignKey(SLAPolicy, null=True, blank=True, on_delete=models.SET_NULL)
    first_response_due_at = models.DateTimeField(null=True, blank=True)
    resolution_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    first_responded_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    ai_summary = models.TextField(blank=True)
    ai_recommendations = models.JSONField(default=dict, blank=True)
    approval_state = models.CharField(max_length=20, default="not_required", choices=[("not_required", "Not required"), ("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")], db_index=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("view_own", "Can view own tickets"), ("view_group", "Can view group tickets"),
            ("view_all", "Can view all tickets"), ("assign", "Can assign tickets"),
            ("export", "Can export tickets"), ("view_sensitive", "Can view sensitive ticket fields"),
            ("view_internal_notes", "Can view internal notes"),
        ]

    def __str__(self):
        return f"{self.reference or 'New'} · {self.subject}"

    @property
    def sla_state(self):
        if self.status in {self.Status.CLOSED}:
            return "closed"
        if self.status in {self.Status.RESOLVED}:
                    return "resolved"
        if self.status == self.Status.PENDING_CUSTOMER:
            return "paused"
        if not self.resolution_due_at:
            return "healthy"
        remaining = self.resolution_due_at - timezone.now()
        if remaining.total_seconds() < 0:
            return "overdue"
        if remaining.total_seconds() < 7200:
            return "at_risk"
        return "healthy"

    @property
    def elapsed_time(self):

        if not self.created_at:
            return None

        end_date = (
            self.updated_at
            or timezone.now()
        )

        duration = (
            end_date
            - self.created_at
        )

        total_seconds = int(
            duration.total_seconds()
        )

        days = total_seconds // 86400

        hours = (
            total_seconds % 86400
        ) // 3600

        minutes = (
            total_seconds % 3600
        ) // 60

        if days > 0:
            return (
                f"{days}d "
                f"{hours}h "
                f"{minutes}m"
            )

        if hours > 0:
            return (
                f"{hours}h "
                f"{minutes}m"
            )

        return f"{minutes}m"

    # =========================================================
    # SLA FULL INFORMATION
    # =========================================================

    @property
    def sla_state_detail(self):

        return {
            "state": self.sla_state,

            "logged_at": (
                self.created_at.isoformat()
                if self.created_at
                else None
            ),

            "last_updated_at": (
                self.updated_at.isoformat()
                if self.updated_at
                else None
            ),

            "elapsed": self.elapsed_time,

            "first_response_due_at": (
                self.first_response_due_at.isoformat()
                if self.first_response_due_at
                else None
            ),

            "resolution_due_at": (
                self.resolution_due_at.isoformat()
                if self.resolution_due_at
                else None
            ),

            "first_responded_at": (
                self.first_responded_at.isoformat()
                if self.first_responded_at
                else None
            ),

            "resolved_at": (
                self.resolved_at.isoformat()
                if self.resolved_at
                else None
            ),

            "closed_at": (
                self.closed_at.isoformat()
                if self.closed_at
                else None
            ),
        }

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.reference:
            self.reference = f"GLIS-{self.created_at:%Y}-{self.pk:05d}"
            super().save(update_fields=["reference"])


class TicketDynamicData(TimeStampedModel):
    ticket = models.OneToOneField(Ticket, related_name="dynamic_data", on_delete=models.CASCADE)
    form_version = models.ForeignKey(DynamicFormVersion, null=True, on_delete=models.SET_NULL)
    values = models.JSONField(default=dict)
    reporting_values = models.JSONField(default=dict, blank=True)
    sensitive_keys = models.JSONField(default=list, blank=True)


class TicketComment(TimeStampedModel):
    ticket = models.ForeignKey(Ticket, related_name="comments", on_delete=models.CASCADE)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.TextField()
    is_internal = models.BooleanField(default=False)
    mentioned_user_ids = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=24,choices=Ticket.Status.choices,null=True,blank=True,)
    
    class Meta:
        ordering = ["created_at"]


class TicketAttachment(TimeStampedModel):
    ticket = models.ForeignKey(Ticket, related_name="attachments", on_delete=models.CASCADE)
    comment = models.ForeignKey(TicketComment,related_name="attachments",on_delete=models.CASCADE,null=True,blank=True,)    
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    file = models.FileField(upload_to="attachments/%Y/%m/", validators=[validate_attachment])
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120)
    size = models.PositiveIntegerField()
    is_restricted = models.BooleanField(default=False)
    scan_status = models.CharField(max_length=20, default="pending", choices=[("pending", "Pending"), ("clean", "Clean"), ("blocked", "Blocked")])
    source_field = models.CharField(max_length=80, blank=True)
    def __str__(self):
        return self.original_name    


class TicketEvent(models.Model):
    ticket = models.ForeignKey(Ticket, related_name="events", on_delete=models.CASCADE)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    event_type = models.CharField(max_length=50)
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]


class RelatedTicket(models.Model):
    source = models.ForeignKey(Ticket, related_name="related_from", on_delete=models.CASCADE)
    target = models.ForeignKey(Ticket, related_name="related_to", on_delete=models.CASCADE)
    relationship = models.CharField(max_length=30, default="related")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source", "target"], name="unique_related_ticket")]


class SavedTicketView(TimeStampedModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=80)
    filters = models.JSONField(default=dict)
    is_default = models.BooleanField(default=False)


class TicketApproval(TimeStampedModel):
    ticket = models.ForeignKey(Ticket, related_name="approvals", on_delete=models.CASCADE)
    step = models.ForeignKey(ApprovalStep, related_name="ticket_approvals", on_delete=models.PROTECT)
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="ticket_approvals", on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default="pending", choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("skipped", "Skipped")])
    decided_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("step__sequence", "created_at")
        constraints = [models.UniqueConstraint(fields=["ticket", "step", "approver"], name="unique_ticket_step_approver")]


class TicketEscalation(TimeStampedModel):
    ticket = models.ForeignKey(Ticket, related_name="escalations", on_delete=models.CASCADE)
    rule = models.ForeignKey(SLAEscalationRule, related_name="ticket_escalations", on_delete=models.PROTECT)
    escalated_to_users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="ticket_escalations", blank=True)
    message = models.CharField(max_length=255)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["ticket", "rule"], name="unique_ticket_escalation_rule")]


class TicketShare(TimeStampedModel):
    ticket = models.ForeignKey(Ticket, related_name="shares", on_delete=models.CASCADE)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="created_ticket_shares", on_delete=models.PROTECT)
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="received_ticket_shares", on_delete=models.CASCADE)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    @property
    def is_valid(self):
        return self.is_active and self.expires_at > timezone.now()


class Notification(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="glis_notifications", on_delete=models.CASCADE)
    ticket = models.ForeignKey(Ticket, null=True, blank=True, related_name="notifications", on_delete=models.CASCADE)
    kind = models.CharField(max_length=30, default="info", choices=[("info", "Information"), ("assignment", "Assignment"), ("approval", "Approval"), ("sla", "SLA escalation"), ("update", "Ticket update")])
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=500, blank=True)
    link = models.CharField(max_length=255, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "read_at", "-created_at"])]
