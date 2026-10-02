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
    TicketOrganization,
    TicketTaggedUser,
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
        "organizations",
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
            "People & organizations",
            {
                "fields": (
                    "organizations",
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


class ScopedTicketAdminMixin:
    def get_queryset(self, request):
        from services.access import TicketAccessPolicy
        from django.db.models import Q
        qs=super().get_queryset(request)
        if request.user.is_superuser:return qs
        ids=TicketAccessPolicy.visible_queryset(request.user).values('pk')
        name=self.model._meta.model_name
        if name=='ticket':return qs.filter(pk__in=ids)
        if name=='relatedticket':return qs.filter(source_id__in=ids,target_id__in=ids)
        if name=='savedticketview':return qs.filter(user=request.user)
        if name=='notification':return qs.filter(Q(ticket_id__in=ids)|Q(ticket__isnull=True),user=request.user)
        return qs.filter(ticket_id__in=ids)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        from services.access import TicketAccessPolicy
        from services.tenancy import visible_users, visible_organizations
        from apps.tpa.models import Policy
        from apps.tpa.services.access import visible_policies
        related=db_field.remote_field.model
        if related is Ticket:kwargs['queryset']=TicketAccessPolicy.visible_queryset(request.user)
        elif related._meta.label_lower=='auth.user':kwargs['queryset']=visible_users(request.user)
        elif related._meta.label_lower=='accounts.organization':kwargs['queryset']=visible_organizations(request.user)
        elif related is Policy:kwargs['queryset']=visible_policies(request.user)
        return super().formfield_for_foreignkey(db_field,request,**kwargs)

    def get_form(self, request, obj=None, **kwargs):
        from services.tenancy import assignable_groups, assignable_users, visible_support_groups
        form=super().get_form(request,obj,**kwargs)
        if self.model is not Ticket:return form
        class ScopedForm(form):
            def __init__(self, *args, **form_kwargs):
                super().__init__(*args,**form_kwargs)
                if obj:
                    for name in ['assignee','assignees']:
                        if name in self.fields:self.fields[name].queryset=assignable_users(request.user,obj)
                if 'groups' in self.fields:self.fields['groups'].queryset=assignable_groups(request.user,obj) if obj else visible_support_groups(request.user)
                if obj and hasattr(obj,'tpa_transaction') and 'status' in self.fields:self.fields['status'].disabled=True
        return ScopedForm


@admin.register(Ticket)
class TicketAdmin(ScopedTicketAdminMixin, JSONModelAdmin):

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
class TicketApprovalAdmin(ScopedTicketAdminMixin, JSONModelAdmin):

    # Decisions must go through the shared service so the assigned actor,
    # audit ledger and linked domain state are updated together.
    # def has_add_permission(self, request):
    #     return False

    # def has_change_permission(self, request, obj=None):
    #     return False

    # def has_delete_permission(self, request, obj=None):
    #     return False

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
class NotificationAdmin(ScopedTicketAdminMixin, JSONModelAdmin):

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
class TicketDynamicDataAdmin(ScopedTicketAdminMixin, JSONModelAdmin):
    pass


# ============================================================
# TICKET EVENT
# ============================================================


@admin.register(TicketEvent)
class TicketEventAdmin(ScopedTicketAdminMixin, JSONModelAdmin):
    pass


# ============================================================
# RELATED TICKET
# ============================================================


@admin.register(RelatedTicket)
class RelatedTicketAdmin(ScopedTicketAdminMixin, JSONModelAdmin):
    pass


# ============================================================
# SAVED TICKET VIEW
# ============================================================


@admin.register(SavedTicketView)
class SavedTicketViewAdmin(ScopedTicketAdminMixin, JSONModelAdmin):
    pass


# ============================================================
# TICKET SHARE
# ============================================================


@admin.register(TicketShare)
class TicketShareAdmin(ScopedTicketAdminMixin, JSONModelAdmin):
    pass


# ============================================================
# TICKET ESCALATION
# ============================================================


@admin.register(TicketEscalation)
class TicketEscalationAdmin(ScopedTicketAdminMixin, JSONModelAdmin):
    pass

@admin.register(TicketOrganization)
class TicketOrganizationAdmin(ScopedTicketAdminMixin, JSONModelAdmin):
    list_display=('ticket','organization','relationship_type','can_view','can_edit','can_assign','can_approve')
    list_filter=('relationship_type','organization')

@admin.register(TicketTaggedUser)
class TicketTaggedUserAdmin(ScopedTicketAdminMixin, JSONModelAdmin):
    list_display=('ticket','user','tagged_by','is_active')
    readonly_fields=('tagged_by',)
    def save_model(self, request, obj, form, change):
        obj.tagged_by=request.user
        super().save_model(request,obj,form,change)
