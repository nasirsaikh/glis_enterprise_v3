from django.contrib import admin, messages
from django.db.models import JSONField
from django.utils import timezone

from django_json_widget.widgets import JSONEditorWidget

from .models import (
    ApprovalStep,
    ApprovalWorkflow,
    Category,
    DynamicFieldSchema,
    DynamicForm,
    DynamicFormVersion,
    FormDataSource,
    Notification,
    Product,
    Project,
    RelatedTicket,
    SavedTicketView,
    SLAEscalationRule,
    SLAPolicy,
    SupportGroup,
    Ticket,
    TicketApproval,
    TicketAttachment,
    TicketComment,
    TicketDynamicData,
    TicketEscalation,
    TicketEvent,
    TicketShare,
)


# ============================================================
# JSON EDITOR
# ============================================================


class AdminJSONEditorWidget(JSONEditorWidget):
    """
    JSON editor for standard Django admin forms.

    IMPORTANT:
    We intentionally DO NOT enable `code` mode.

    JSONEditor's `code` mode uses Ace Editor, which creates
    workers and loads data: scripts using importScripts().
    That conflicts with a strict CSP.

    `text` mode provides raw JSON editing without Ace workers.
    """

    def __init__(self, attrs=None, **kwargs):
        super().__init__(
            attrs=attrs,
            width="100%",
            height="450px",
            options={
                "mode": "tree",

                "modes": [
                    "tree",
                    "text",
                    "view",
                ],

                "search": True,
                "navigationBar": True,
                "statusBar": True,
                "mainMenuBar": True,
            },
        )


class InlineJSONEditorWidget(JSONEditorWidget):
    """
    Slightly smaller JSON editor for Django admin inlines.
    """

    def __init__(self, attrs=None, **kwargs):
        super().__init__(
            attrs=attrs,
            width="100%",
            height="300px",
            options={
                "mode": "tree",

                "modes": [
                    "tree",
                    "text",
                    "view",
                ],

                "search": True,
                "navigationBar": True,
                "statusBar": False,
                "mainMenuBar": True,
            },
        )


# ============================================================
# BASE ADMIN CLASSES
# ============================================================


class JSONModelAdmin(admin.ModelAdmin):
    """
    All JSONField fields automatically use our JSON editor.
    """

    formfield_overrides = {
        JSONField: {
            "widget": AdminJSONEditorWidget,
        },
    }


class JSONStackedInline(admin.StackedInline):
    """
    JSON-enabled StackedInline.
    """

    formfield_overrides = {
        JSONField: {
            "widget": InlineJSONEditorWidget,
        },
    }


class JSONTabularInline(admin.TabularInline):
    """
    JSON-enabled TabularInline.
    """

    formfield_overrides = {
        JSONField: {
            "widget": InlineJSONEditorWidget,
        },
    }


# ============================================================
# PROJECT / PRODUCT
# ============================================================


class ProductInline(JSONTabularInline):
    model = Product
    extra = 0


@admin.register(Project)
class ProjectAdmin(JSONModelAdmin):

    list_display = (
        "code",
        "name_en",
        "is_active",
        "updated_at",
    )

    list_filter = (
        "is_active",
    )

    filter_horizontal = (
        "groups",
        "members",
    )

    inlines = [
        ProductInline,
    ]


@admin.register(Product)
class ProductAdmin(JSONModelAdmin):

    list_display = (
        "name_en",
        "code",
        "project",
        "is_active",
    )

    list_filter = (
        "project",
        "is_active",
    )


# ============================================================
# CATEGORY
# ============================================================


@admin.register(Category)
class CategoryAdmin(JSONModelAdmin):

    list_display = (
        "name_en",
        "code",
        "product",
        "default_priority",
        "default_group",
        "default_user",
        "approval_workflow",
        "auto_close_days",
        "is_active",
    )

    list_filter = (
        "product__project",
        "product",
        "default_priority",
        "is_active",
    )

    search_fields = (
        "name_en",
        "name_ar",
        "code",
    )

    filter_horizontal = (
        "default_groups",
    )

    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    "product",
                    "parent",
                    "code",
                    "name_en",
                    "name_ar",
                    "is_active",
                )
            },
        ),
        (
            "Routing defaults",
            {
                "fields": (
                    "default_priority",
                    "default_group",
                    "default_groups",
                    "default_user",
                )
            },
        ),
        (
            "Documents and approvals",
            {
                "fields": (
                    "required_documents",
                    "approval_workflow",
                )
            },
        ),
        (
            "Lifecycle and communications",
            {
                "fields": (
                    "auto_close_days",
                    "reopen_allowed_days",
                    "send_initial_email",
                    "send_update_email",
                    "ai_enabled",
                )
            },
        ),
    )


# ============================================================
# SUPPORT GROUP
# ============================================================


@admin.register(SupportGroup)
class SupportGroupAdmin(JSONModelAdmin):

    list_display = (
        "name",
        "code",
        "is_active",
        "can_view_sensitive",
        "can_access_reports",
    )

    filter_horizontal = (
        "members",
        "managers",
    )

    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    "name",
                    "code",
                    "description",
                    "auth_group",
                    "is_active",
                )
            },
        ),

        (
            "People",
            {
                "fields": (
                    "members",
                    "managers",
                )
            },
        ),

        (
            "Ticket capabilities",
            {
                "fields": (
                    "can_view_all_group_tickets",
                    "can_edit_group_tickets",
                    "can_assign_group_tickets",
                    "can_view_sensitive",
                    "can_view_internal_notes",
                    "can_view_restricted_attachments",
                    "can_access_reports",
                )
            },
        ),

        (
            "Routing",
            {
                "fields": (
                    "routing_config",
                )
            },
        ),
    )


# ============================================================
# DYNAMIC FIELD INLINE
# ============================================================


class DynamicFieldInline(JSONStackedInline):

    model = DynamicFieldSchema

    extra = 0

    fields = (
        "order",
        "name",
        "label_en",
        "label_ar",
        "control",
        "required",
        "configuration",
    )


# ============================================================
# DYNAMIC FORM VERSION
# ============================================================


@admin.register(DynamicFormVersion)
class DynamicFormVersionAdmin(JSONModelAdmin):

    list_display = (
        "form",
        "version",
        "state",
        "created_by",
        "published_at",
    )

    list_filter = (
        "state",
        "form",
    )

    inlines = [
        DynamicFieldInline,
    ]

    actions = (
        "publish_selected",
        "activate_selected",
    )

    @admin.action(
        description="Validate and publish selected version"
    )
    def publish_selected(self, request, queryset):

        for version in queryset.select_related("form"):

            fields = (
                version.schema.get("fields")
                if isinstance(version.schema, dict)
                else None
            )

            names = [
                field.get("name")
                for field in (fields or [])
            ]

            if (
                fields is None
                or any(not name for name in names)
                or len(names) != len(set(names))
            ):

                self.message_user(
                    request,
                    f"{version}: schema must contain uniquely named fields.",
                    messages.ERROR,
                )

                continue

            version.form.versions.filter(
                state="published"
            ).exclude(
                pk=version.pk
            ).update(
                state="archived"
            )

            version.state = "published"
            version.published_at = timezone.now()
            version.validation_errors = []

            version.save(
                update_fields=[
                    "state",
                    "published_at",
                    "validation_errors",
                    "updated_at",
                ]
            )

            version.form.active_version = version

            version.form.save(
                update_fields=[
                    "active_version",
                ]
            )

            self.message_user(
                request,
                f"{version} published successfully.",
                messages.SUCCESS,
            )

    @admin.action(
        description="Activate selected published version"
    )
    def activate_selected(self, request, queryset):

        activated = 0

        for version in queryset.filter(
            state="published"
        ).select_related("form"):

            version.form.active_version = version

            version.form.save(
                update_fields=[
                    "active_version",
                ]
            )

            activated += 1

        if activated:

            self.message_user(
                request,
                f"{activated} version(s) activated successfully.",
                messages.SUCCESS,
            )

        else:

            self.message_user(
                request,
                "No published versions selected.",
                messages.WARNING,
            )


# ============================================================
# DYNAMIC FORM
# ============================================================


@admin.register(DynamicForm)
class DynamicFormAdmin(JSONModelAdmin):

    list_display = (
        "name_en",
        "key",
        "project",
        "product",
        "category",
        "active_version",
        "is_active",
    )

    list_filter = (
        "is_active",
        "project",
        "product",
    )

    search_fields = (
        "name_en",
        "name_ar",
        "key",
    )


# ============================================================
# COMMENTS
# ============================================================


class CommentInline(JSONTabularInline):

    model = TicketComment

    extra = 0

    readonly_fields = (
        "author",
        "body",
        "is_internal",
        "created_at",
    )


# ============================================================
# ATTACHMENTS
# ============================================================


class AttachmentInline(JSONTabularInline):

    model = TicketAttachment

    extra = 0

    readonly_fields = (
        "uploaded_by",
        "original_name",
        "content_type",
        "size",
        "source_field",
        "created_at",
    )


# ============================================================
# TICKET
# ============================================================


@admin.register(Ticket)
class TicketAdmin(JSONModelAdmin):

    list_display = (
        "reference",
        "subject",
        "status",
        "priority",
        "project",
        "requester",
        "assignee",
        "sla_state",
        "created_at",
    )

    list_filter = (
        "status",
        "priority",
        "project",
        "product",
        "category",
        "is_sensitive",
        "visibility",
    )

    search_fields = (
        "reference",
        "subject",
        "description",
        "requester__email",
    )

    filter_horizontal = (
        "groups",
        "assignees",
    )

    readonly_fields = (
        "reference",
        "created_at",
        "updated_at",
        "ai_summary",
        "ai_recommendations",
    )

    inlines = [
        CommentInline,
        AttachmentInline,
    ]


# ============================================================
# APPROVAL STEP INLINE
# ============================================================


class ApprovalStepInline(JSONStackedInline):

    model = ApprovalStep

    extra = 0

    filter_horizontal = (
        "approver_users",
        "approver_groups",
    )


# ============================================================
# APPROVAL WORKFLOW
# ============================================================


@admin.register(ApprovalWorkflow)
class ApprovalWorkflowAdmin(JSONModelAdmin):

    list_display = (
        "name",
        "is_active",
        "updated_at",
    )

    list_filter = (
        "is_active",
    )

    inlines = (
        ApprovalStepInline,
    )


# ============================================================
# APPROVAL STEP
# ============================================================


@admin.register(ApprovalStep)
class ApprovalStepAdmin(JSONModelAdmin):

    list_display = (
        "workflow",
        "sequence",
        "name",
        "approvals_required",
        "escalation_after_hours",
    )

    list_filter = (
        "workflow",
    )

    filter_horizontal = (
        "approver_users",
        "approver_groups",
    )


# ============================================================
# SLA ESCALATION INLINE
# ============================================================


class SLAEscalationInline(JSONStackedInline):

    model = SLAEscalationRule

    extra = 0

    filter_horizontal = (
        "target_users",
        "target_groups",
    )


# ============================================================
# SLA POLICY
# ============================================================


@admin.register(SLAPolicy)
class SLAPolicyAdmin(JSONModelAdmin):

    list_display = (
        "name",
        "project",
        "category",
        "priority",
        "first_response_minutes",
        "resolution_minutes",
        "is_active",
    )

    list_filter = (
        "priority",
        "is_active",
        "project",
        "category",
    )

    inlines = (
        SLAEscalationInline,
    )


# ============================================================
# SLA ESCALATION RULE
# ============================================================


@admin.register(SLAEscalationRule)
class SLAEscalationRuleAdmin(JSONModelAdmin):

    list_display = (
        "policy",
        "level",
        "trigger_after_minutes",
        "include_assignee_reporting_manager",
        "is_active",
    )

    filter_horizontal = (
        "target_users",
        "target_groups",
    )


# ============================================================
# TICKET APPROVAL
# ============================================================


@admin.register(TicketApproval)
class TicketApprovalAdmin(JSONModelAdmin):

    list_display = (
        "ticket",
        "step",
        "approver",
        "status",
        "decided_at",
    )

    list_filter = (
        "status",
        "step__workflow",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "decided_at",
    )


# ============================================================
# NOTIFICATION
# ============================================================


@admin.register(Notification)
class NotificationAdmin(JSONModelAdmin):

    list_display = (
        "created_at",
        "user",
        "kind",
        "title",
        "ticket",
        "read_at",
    )

    list_filter = (
        "kind",
        "read_at",
    )

    search_fields = (
        "user__email",
        "title",
        "body",
        "ticket__reference",
    )


# ============================================================
# FORM DATA SOURCE
# ============================================================


@admin.register(FormDataSource)
class FormDataSourceAdmin(JSONModelAdmin):
    pass


# ============================================================
# TICKET DYNAMIC DATA
# ============================================================


@admin.register(TicketDynamicData)
class TicketDynamicDataAdmin(JSONModelAdmin):
    pass


# ============================================================
# TICKET EVENT
# ============================================================


@admin.register(TicketEvent)
class TicketEventAdmin(JSONModelAdmin):
    pass


# ============================================================
# RELATED TICKET
# ============================================================


@admin.register(RelatedTicket)
class RelatedTicketAdmin(JSONModelAdmin):
    pass


# ============================================================
# SAVED TICKET VIEW
# ============================================================


@admin.register(SavedTicketView)
class SavedTicketViewAdmin(JSONModelAdmin):
    pass


# ============================================================
# TICKET SHARE
# ============================================================


@admin.register(TicketShare)
class TicketShareAdmin(JSONModelAdmin):
    pass


# ============================================================
# TICKET ESCALATION
# ============================================================


@admin.register(TicketEscalation)
class TicketEscalationAdmin(JSONModelAdmin):
    pass