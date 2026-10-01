import hashlib
import mimetypes

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect

from .services.access import visible_inbound_emails
from .services.email_reprocessing import (
    email_reprocessing_pending,
    queue_email_reprocessing,
    validate_email_reprocessing,
)

from .models import (
    BenefitPlan,
    CardDispatch,
    ExtractionAttempt,
    InboundEmail,
    InboundEmailAttachment,
    Member,
    MemberAction,
    MemberPolicyEnrollment,
    MemberTransaction,
    Policy,
    PolicyAccess,
    SourceDocument,
    TPAEmailAuthority,
    TPAMailboxSyncState,
    TPAOrganization,
    TransactionEvent,
    TransactionQuery,
    TransactionQueryMessage,
)


@admin.register(TPAOrganization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("code", "name_en", "organization_type", "is_active")
    list_filter = ("organization_type", "is_active")
    search_fields = ("code", "name_en", "name_ar", "commercial_registration")


@admin.register(Policy)
class PolicyAdmin(admin.ModelAdmin):
    list_display = (
        "policy_number",
        "sponsor",
        "insurance_company",
        "tpa_organization",
        "status",
        "start_date",
        "expiry_date",
        "stp_enabled",
        "initial_enrollment_completed_at",
    )
    list_filter = ("status", "product_type", "stp_enabled")
    search_fields = ("policy_number", "policy_name")


@admin.register(BenefitPlan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("policy", "code", "name", "annual_premium", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "policy__policy_number")


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = (
        "tpa_member_id",
        "employee_id",
        "full_name",
        "sponsor",
        "relationship",
        "principal",
        "status",
    )
    list_filter = ("relationship", "status")
    search_fields = (
        "tpa_member_id",
        "employee_id",
        "first_name",
        "last_name",
        "national_id",
        "passport_number",
    )


@admin.register(MemberPolicyEnrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = (
        "member",
        "policy",
        "benefit_plan",
        "coverage_start_date",
        "coverage_end_date",
        "card_number",
        "premium_amount",
        "enrollment_status",
    )
    list_filter = ("enrollment_status",)


@admin.register(MemberTransaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "policy",
        "transaction_type",
        "source",
        "status",
        "validation_score",
        "stp_eligible",
        "refund_basis",
        "expected_reactivation_date",
        "ticket",
    )
    list_filter = ("transaction_type", "source", "status", "stp_eligible", "refund_basis")
    search_fields = ("reference", "policy__policy_number", "ticket__reference")
    readonly_fields = ("reference", "submitted_at", "processed_at", "approved_at")


@admin.register(MemberAction)
class ActionAdmin(admin.ModelAdmin):
    list_display = (
        "transaction",
        "row_number",
        "action",
        "validation_status",
        "extraction_confidence",
        "calculated_premium",
        "card_number",
        "tpa_effective_date",
        "tpa_premium_amount",
    )
    list_filter = ("validation_status", "action")


@admin.register(PolicyAccess)
class PolicyAccessAdmin(admin.ModelAdmin):
    list_display = (
        "organization",
        "policy",
        "user",
        "can_view",
        "can_create_enrollment",
        "can_create_endorsement",
        "can_approve",
        "can_process",
        "active",
    )
    list_filter = ("active", "can_approve", "can_process")


@admin.register(TransactionEvent)
class EventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "transaction", "event_type", "actor", "summary")
    list_filter = ("event_type",)
    readonly_fields = (
        "transaction",
        "actor",
        "event_type",
        "summary",
        "details",
        "created_at",
        "updated_at",
    )


@admin.register(SourceDocument)
class SourceDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "original_name",
        "transaction",
        "document_kind",
        "extraction_method",
        "processing_state",
        "processed",
        "extraction_confidence",
    )
    list_filter = ("processing_state", "processed", "document_kind", "extraction_method")
    search_fields = ("original_name", "transaction__reference", "source_hash")
    readonly_fields = ("source_hash", "extracted_payload", "processing_error")


class InboundEmailAttachmentInline(admin.TabularInline):
    model = InboundEmailAttachment
    extra = 0
    fields = (
        "file",
        "original_name",
        "content_type",
        "size",
        "processing_state",
        "processing_error",
    )
    readonly_fields = (
        "content_type",
        "size",
        "processing_state",
        "processing_error",
    )


@admin.register(InboundEmail)
class InboundEmailAdmin(admin.ModelAdmin):
    change_form_template = "admin/tpa/inboundemail/change_form.html"
    actions = ("reprocess_selected_emails",)
    list_display = (
        "received_at",
        "sender",
        "subject",
        "provider",
        "mailbox",
        "classification",
        "processing_state",
        "processing_stage",
        "ai_provider_name",
        "ai_model_name",
        "ai_confidence",
        "transaction",
        "created_by",
    )
    list_filter = ("provider", "processing_state", "classification", "mailbox")
    search_fields = (
        "provider_message_id",
        "graph_message_id",
        "internet_message_id",
        "conversation_id",
        "sender",
        "recipient",
        "subject",
        "transaction__reference",
    )
    readonly_fields = (
        "transaction",
        "processing_state",
        "processing_stage",
        "raw_ai_output",
        "ai_extracted_payload",
        "ai_provider_name",
        "ai_model_name",
        "ai_confidence",
        "classification_confidence",
        "processing_error",
        "processed_at",
    )
    inlines = (InboundEmailAttachmentInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).filter(
            pk__in=visible_inbound_emails(request.user).values("pk")
        )

    def save_formset(self, request, form, formset, change):
        if formset.model is not InboundEmailAttachment:
            return super().save_formset(request, form, formset, change)
        attachments = formset.save(commit=False)
        for deleted in formset.deleted_objects:
            deleted.delete()
        for attachment in attachments:
            attachment.file.open("rb")
            try:
                digest = hashlib.sha256()
                for chunk in attachment.file.chunks():
                    digest.update(chunk)
                new_hash = digest.hexdigest()
                if attachment.sha256 != new_hash:
                    attachment.processing_state = InboundEmailAttachment.State.RECEIVED
                    attachment.processing_error = ""
                    attachment.extracted_payload = {}
                attachment.sha256 = new_hash
                attachment.size = attachment.file.size
                attachment.content_type = (
                    getattr(attachment.file.file, "content_type", "")
                    or mimetypes.guess_type(attachment.original_name)[0] or "application/octet-stream"
                )
                attachment.save()
            finally:
                attachment.file.close()
        formset.save_m2m()

    @admin.action(description="Reprocess selected emails", permissions=["change"])
    def reprocess_selected_emails(self, request, queryset):
        queued = 0
        failures = []
        for email in queryset:
            try:
                if not self.has_change_permission(request, email):
                    raise PermissionDenied("Inbound email change permission is required.")
                job = queue_email_reprocessing(email, request.user)
            except (PermissionDenied, ValueError) as exc:
                failures.append(f"Email #{email.pk}: {exc}")
                continue
            self.log_change(request, email, f"Queued email reprocessing (job #{job.pk}).")
            queued += 1
        if queued:
            self.message_user(
                request,
                f"{queued} email(s) queued for reprocessing. Refresh the list to see processing status and errors.",
                messages.SUCCESS,
            )
        if failures:
            self.message_user(
                request,
                f"{len(failures)} email(s) could not be queued. " + " ".join(failures[:5]),
                messages.WARNING,
            )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        context = {**(extra_context or {}), "can_reprocess_email": False}
        email = self.get_object(request, object_id)
        if email is not None and self.has_change_permission(request, email):
            try:
                validate_email_reprocessing(email, request.user)
                if email.processing_state == InboundEmail.State.PROCESSING:
                    raise ValueError("This email is already being processed.")
                if email_reprocessing_pending(email):
                    raise ValueError("This email is queued for reprocessing. Refresh to see the result.")
            except (PermissionDenied, ValueError) as exc:
                context["email_reprocess_unavailable_reason"] = str(exc)
            else:
                context["can_reprocess_email"] = True
        return super().change_view(request, object_id, form_url, context)

    def response_change(self, request, obj):
        if "_reprocess" in request.POST:
            try:
                job = queue_email_reprocessing(obj, request.user)
            except (PermissionDenied, ValueError) as exc:
                self.message_user(request, f"Email saved. Reprocessing was not queued: {exc}", messages.WARNING)
            else:
                self.log_change(request, obj, f"Queued email reprocessing (job #{job.pk}).")
                self.message_user(
                    request,
                    f"Email saved and queued for reprocessing (job #{job.pk}). Refresh to see processing status and errors.",
                    messages.SUCCESS,
                )
            return HttpResponseRedirect(request.path)
        return super().response_change(request, obj)


@admin.register(InboundEmailAttachment)
class InboundEmailAttachmentAdmin(admin.ModelAdmin):
    list_display = (
        "original_name",
        "inbound_email",
        "content_type",
        "size",
        "processing_state",
    )
    list_filter = ("processing_state", "content_type")
    search_fields = (
        "original_name",
        "inbound_email__subject",
        "sha256",
    )
    readonly_fields = (
        "sha256",
        "extracted_payload",
        "processing_error",
    )



class TransactionQueryMessageInline(admin.TabularInline):
    model = TransactionQueryMessage
    extra = 0
    readonly_fields = ("ticket_comment", "sender", "kind", "audience", "created_at")


@admin.register(TransactionQuery)
class TransactionQueryAdmin(admin.ModelAdmin):
    list_display = (
        "transaction",
        "subject",
        "purpose",
        "audience",
        "status",
        "raised_by",
        "resolved_by",
        "resolved_at",
        "created_at",
    )
    list_filter = ("status", "purpose", "audience")
    search_fields = (
        "transaction__reference",
        "subject",
        "raised_by__username",
    )
    readonly_fields = (
        "transaction",
        "raised_by",
        "pre_query_status",
        "resolved_by",
        "resolved_at",
        "created_at",
        "updated_at",
    )
    inlines = (TransactionQueryMessageInline,)


@admin.register(TransactionQueryMessage)
class TransactionQueryMessageAdmin(admin.ModelAdmin):
    list_display = (
        "query",
        "sender",
        "kind",
        "audience",
        "ticket_comment",
        "created_at",
    )
    list_filter = ("kind", "audience")
    search_fields = (
        "query__transaction__reference",
        "query__subject",
        "sender__username",
        "ticket_comment__body",
    )
    readonly_fields = (
        "query",
        "ticket_comment",
        "sender",
        "kind",
        "created_at",
        "updated_at",
    )



@admin.register(TPAEmailAuthority)
class TPAEmailAuthorityAdmin(admin.ModelAdmin):
    list_display = (
        "email_address",
        "organization",
        "policy",
        "active",
        "valid_from",
        "valid_until",
    )
    list_filter = ("active", "organization")
    search_fields = ("email_address", "organization__name_en", "policy__policy_number")
    filter_horizontal = ()


@admin.register(TPAMailboxSyncState)
class TPAMailboxSyncStateAdmin(admin.ModelAdmin):
    list_display = (
        "provider",
        "mailbox",
        "folder",
        "last_successful_at",
        "last_attempted_at",
        "messages_processed",
        "messages_review",
        "messages_ignored",
        "messages_failed",
    )
    readonly_fields = (
        "delta_link",
        "last_attempted_at",
        "last_successful_at",
        "last_error",
        "messages_processed",
        "messages_review",
        "messages_ignored",
        "messages_failed",
        "created_at",
        "updated_at",
    )


@admin.register(ExtractionAttempt)
class ExtractionAttemptAdmin(admin.ModelAdmin):
    list_display = ("created_at", "stage", "status", "provider", "model_name")
    list_filter = ("status", "stage")
    readonly_fields = (
        "source_document",
        "inbound_attachment",
        "provider",
        "stage",
        "status",
        "model_name",
        "error",
        "raw_output",
        "metadata",
        "created_at",
        "updated_at",
    )


@admin.register(CardDispatch)
class CardDispatchAdmin(admin.ModelAdmin):
    list_display = (
        "transaction",
        "method",
        "status",
        "tracking_number",
        "dispatched_at",
        "delivered_or_collected_at",
        "recorded_by",
    )
    list_filter = ("method", "status")
    search_fields = ("transaction__reference", "tracking_number", "recipient_name")
