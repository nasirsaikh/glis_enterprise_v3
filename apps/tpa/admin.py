from django.contrib import admin

from .models import (
    BenefitPlan,
    InboundEmail,
    InboundEmailAttachment,
    Member,
    MemberAction,
    MemberPolicyEnrollment,
    MemberTransaction,
    Policy,
    PolicyAccess,
    SourceDocument,
    TPAOrganization,
    TransactionEvent,
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
        "status",
        "start_date",
        "expiry_date",
        "stp_enabled",
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
        "ticket",
    )
    list_filter = ("transaction_type", "source", "status", "stp_eligible")
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
        "processed",
        "extraction_confidence",
    )
    list_filter = ("processed", "document_kind", "extraction_method")
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
    list_display = (
        "received_at",
        "sender",
        "subject",
        "provider",
        "processing_state",
        "ai_confidence",
        "transaction",
        "created_by",
    )
    list_filter = ("provider", "processing_state")
    search_fields = (
        "provider_message_id",
        "sender",
        "recipient",
        "subject",
        "transaction__reference",
    )
    readonly_fields = (
        "ai_extracted_payload",
        "ai_confidence",
        "processing_error",
        "processed_at",
    )
    inlines = (InboundEmailAttachmentInline,)


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
