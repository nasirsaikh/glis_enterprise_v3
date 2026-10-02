from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from apps.accounts.models import Organization
from apps.core.models import TimeStampedModel

class Policy(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT="draft","Draft"; ACTIVE="active","Active"; SUSPENDED="suspended","Suspended"; EXPIRED="expired","Expired"; CANCELLED="cancelled","Cancelled"
    organization=models.ForeignKey(
        Organization,
        related_name="policies",
        on_delete=models.PROTECT,
    )
    policy_number=models.CharField(max_length=80, unique=True, db_index=True)
    policy_name=models.CharField(max_length=180, blank=True)
    start_date=models.DateField()
    expiry_date=models.DateField()
    status=models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    product=models.ForeignKey("tickets.Product", null=True, blank=True, on_delete=models.PROTECT, related_name="policies")
    policy_type=models.CharField(max_length=80, default="GROUP_MEDICAL")
    workflow_organizations=models.ManyToManyField(Organization, blank=True, related_name="workflow_policies")
    product_type=models.CharField(max_length=80, default="MEDICAL")
    insurer_reference=models.CharField(max_length=100, blank=True)
    tpa_reference=models.CharField(max_length=100, blank=True)
    cancellation_effective_date=models.DateField(null=True, blank=True)
    currency=models.CharField(max_length=3, default="OMR")
    stp_enabled=models.BooleanField(default=False)
    premium_calculation_enabled=models.BooleanField(default=True)
    allowed_backdating_days=models.PositiveSmallIntegerField(default=30)
    validation_bypass_allowed=models.BooleanField(default=False)
    physical_card_required=models.BooleanField(default=False)
    configuration=models.JSONField(default=dict, blank=True)
    initial_enrollment_completed_at=models.DateTimeField(null=True, blank=True)
    initial_enrollment_completed_by=models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="completed_tpa_policy_enrollments",
        on_delete=models.SET_NULL,
    )
    notes=models.TextField(blank=True)
    def clean(self):
        if self.expiry_date and self.start_date and self.expiry_date < self.start_date:
            raise ValidationError({"expiry_date":"Expiry date cannot be before start date."})
    def __str__(self): return self.policy_number

class BenefitPlan(TimeStampedModel):
    policy=models.ForeignKey(Policy, related_name="plans", on_delete=models.CASCADE)
    code=models.CharField(max_length=50)
    name=models.CharField(max_length=160)
    description=models.TextField(blank=True)
    annual_premium=models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    default_sum_insured=models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    premium_configuration=models.JSONField(default=dict, blank=True)
    is_active=models.BooleanField(default=True)
    effective_from=models.DateField(null=True, blank=True)
    effective_until=models.DateField(null=True, blank=True)
    def clean(self):
        errors = {}
        if self.annual_premium is not None and self.annual_premium < 0:
            errors['annual_premium'] = 'Premium cannot be negative.'
        if self.default_sum_insured is not None and self.default_sum_insured < 0:
            errors['default_sum_insured'] = 'Sum insured cannot be negative.'
        if self.effective_from and self.effective_until and self.effective_until < self.effective_from:
            errors['effective_until'] = 'End date cannot precede start date.'
        if errors:
            raise ValidationError(errors)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["policy","code"], name="tpa_unique_policy_plan"),
            models.CheckConstraint(condition=models.Q(annual_premium__gte=0), name='plan_nonnegative_premium'),
            models.CheckConstraint(condition=models.Q(default_sum_insured__isnull=True) | models.Q(default_sum_insured__gte=0), name='plan_nonnegative_sum'),
            models.CheckConstraint(condition=models.Q(effective_from__isnull=True) | models.Q(effective_until__isnull=True) | models.Q(effective_until__gte=models.F('effective_from')), name='plan_valid_dates')]
    def __str__(self): return f"{self.policy.policy_number} · {self.code}"

class Member(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE="active","Active"
        SUSPENDED="suspended","Temporarily Suspended"
        TERMINATED="terminated","Terminated"
        VOIDED="voided","Deleted / Voided"
        CANCELLED="cancelled","Cancelled"
    class Relationship(models.TextChoices):
        PRINCIPAL="PRINCIPAL","Principal"; SPOUSE="SPOUSE","Spouse"; CHILD="CHILD","Child"; OTHER="OTHER","Other"
    tpa_member_id=models.CharField(max_length=40, unique=True, null=True, blank=True, editable=False)
    organization=models.ForeignKey(Organization, related_name="members", on_delete=models.PROTECT)
    employee_id=models.CharField(max_length=80, blank=True, db_index=True)
    first_name=models.CharField(max_length=100)
    middle_name=models.CharField(max_length=100, blank=True)
    last_name=models.CharField(max_length=100)
    date_of_birth=models.DateField()
    gender=models.CharField(max_length=20)
    relationship=models.CharField(max_length=20, choices=Relationship.choices)
    national_id=models.CharField(max_length=80, blank=True, db_index=True)
    passport_number=models.CharField(max_length=80, blank=True, db_index=True)
    principal=models.ForeignKey("self", null=True, blank=True, related_name="dependents", on_delete=models.PROTECT)
    status=models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    @property
    def full_name(self): return " ".join(x for x in [self.first_name,self.middle_name,self.last_name] if x)
    def save(self,*args,**kwargs):
        new=self.pk is None
        super().save(*args,**kwargs)
        if new and not self.tpa_member_id:
            self.tpa_member_id=f"TPA-{self.created_at:%Y}-{self.pk:06d}"
            super().save(update_fields=["tpa_member_id"])
    def __str__(self): return f"{self.tpa_member_id or 'New'} · {self.full_name}"

class MemberPolicyEnrollment(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING="pending","Pending"
        ACTIVE="active","Active"
        SUSPENDED="suspended","Temporarily Suspended"
        TERMINATED="terminated","Terminated"
        VOIDED="voided","Voided"
        CANCELLED="cancelled","Cancelled"
    member=models.ForeignKey(Member, related_name="enrollments", on_delete=models.PROTECT)
    policy=models.ForeignKey(Policy, related_name="enrollments", on_delete=models.PROTECT)
    benefit_plan=models.ForeignKey(BenefitPlan, related_name="enrollments", on_delete=models.PROTECT)
    coverage_start_date=models.DateField()
    coverage_end_date=models.DateField(null=True, blank=True)
    enrollment_status=models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    card_number=models.CharField(max_length=100, blank=True)
    premium_amount=models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    premium_calculation_basis=models.JSONField(default=dict, blank=True)
    termination_reason=models.TextField(blank=True)
    termination_date=models.DateField(null=True, blank=True)
    voided_at=models.DateTimeField(null=True, blank=True)
    cancellation_date=models.DateField(null=True, blank=True)
    suspension_date=models.DateField(null=True, blank=True)
    suspension_reason=models.TextField(blank=True)
    expected_reactivation_date=models.DateField(null=True, blank=True)
    reactivation_date=models.DateField(null=True, blank=True)

class MemberTransaction(TimeStampedModel):
    class Type(models.TextChoices):
        NEW_POLICY_ENROLLMENT="NEW_POLICY_ENROLLMENT","New Policy Enrollment"
        MEMBER_ADD="MEMBER_ADD","Member Addition"
        MEMBER_UPDATE="MEMBER_UPDATE","Member Demographic Change"
        MEMBER_TERMINATE="MEMBER_TERMINATE","Member Termination"
        MEMBER_SUSPEND="MEMBER_SUSPEND","Temporary Suspension"
        MEMBER_REACTIVATE="MEMBER_REACTIVATE","Member Reactivation"
        MEMBER_DELETE="MEMBER_DELETE","Member Deletion / Void"
        POLICY_CANCEL="POLICY_CANCEL","Policy Cancellation"
    class RefundBasis(models.TextChoices):
        NONE="NONE","Not Applicable"
        FULL="FULL","Full Refund"
        PRO_RATA="PRO_RATA","Pro-Rata Refund"
    class Source(models.TextChoices):
        PORTAL="PORTAL","Portal"; EMAIL="EMAIL","Email"; API="API","API"; ADMIN="ADMIN","Admin"; IMPORT="IMPORT","Import"
    class Status(models.TextChoices):
        DRAFT="draft","Draft"; EXTRACTING="extracting","Extracting"; PENDING_VALIDATION="pending_validation","Pending Validation"
        NEEDS_INFORMATION="needs_information","Needs Information"; VALIDATION_FAILED="validation_failed","Validation Failed"
        PENDING_APPROVAL="pending_approval","Pending Approval"; APPROVED="approved","Approved"; AUTO_APPROVED="auto_approved","Auto Approved"
        SENT_TO_TPA="sent_to_tpa","Sent to TPA"; TPA_IN_PROGRESS="tpa_in_progress","TPA In Progress"; TPA_QUERY="tpa_query","TPA Query"
        CARD_DISPATCH="card_dispatch","Card Dispatch"
        PROCESSING="processing","Processing"; PROCESSED="processed","Processed"; COMPLETED="completed","Completed"; REJECTED="rejected","Rejected"; FAILED="failed","Failed"; CANCELLED="cancelled","Cancelled"
    reference=models.CharField(max_length=80, unique=True, null=True, blank=True, editable=False)
    organization=models.ForeignKey(Organization, related_name="transactions", on_delete=models.PROTECT)
    insurer=models.ForeignKey(Organization, related_name="insurer_transactions", on_delete=models.PROTECT)
    policy=models.ForeignKey(Policy, related_name="transactions", on_delete=models.PROTECT)
    transaction_type=models.CharField(max_length=30, choices=Type.choices, db_index=True)
    source=models.CharField(max_length=20, choices=Source.choices, default=Source.PORTAL)
    request_date=models.DateTimeField(auto_now_add=True)
    effective_date=models.DateField()
    status=models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT, db_index=True)
    requester=models.ForeignKey(settings.AUTH_USER_MODEL, related_name="tpa_transactions", on_delete=models.PROTECT)
    requester_organization=models.ForeignKey(Organization, related_name="requested_transactions", on_delete=models.PROTECT)
    ticket=models.OneToOneField("tickets.Ticket", related_name="tpa_transaction", on_delete=models.PROTECT)
    premium_before=models.DecimalField(max_digits=16, decimal_places=3, default=Decimal("0"))
    premium_adjustment=models.DecimalField(max_digits=16, decimal_places=3, default=Decimal("0"))
    premium_after=models.DecimalField(max_digits=16, decimal_places=3, default=Decimal("0"))
    currency=models.CharField(max_length=3, default="OMR")
    validation_score=models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    stp_eligible=models.BooleanField(default=False)
    stp_blockers=models.JSONField(default=list, blank=True)
    ai_summary=models.TextField(blank=True)
    ai_extraction_status=models.CharField(max_length=30, blank=True)
    validation_bypassed=models.BooleanField(default=False)
    validation_bypass_reason=models.TextField(blank=True)
    validation_bypassed_by=models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="tpa_validation_bypasses", on_delete=models.SET_NULL)
    validation_bypassed_at=models.DateTimeField(null=True, blank=True)
    remarks=models.TextField(blank=True)
    refund_basis=models.CharField(max_length=20, choices=RefundBasis.choices, default=RefundBasis.NONE, db_index=True)
    expected_reactivation_date=models.DateField(null=True, blank=True)
    classification=models.CharField(max_length=40, blank=True, db_index=True)
    classification_confidence=models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    validation_completed_at=models.DateTimeField(null=True, blank=True)
    physical_card_required=models.BooleanField(default=False)
    submitted_at=models.DateTimeField(null=True, blank=True)
    processed_at=models.DateTimeField(null=True, blank=True)
    approved_at=models.DateTimeField(null=True, blank=True)
    approved_by=models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="approved_tpa_transactions", on_delete=models.SET_NULL)
    rejection_reason=models.TextField(blank=True)
    metadata=models.JSONField(default=dict, blank=True)
    class Meta:
        permissions=[
            ("view_tpa_dashboard","Can view TPA dashboard"),("create_enrollment","Can create TPA enrollment"),
            ("create_endorsement","Can create TPA endorsement"),("terminate_member","Can terminate TPA member"),
            ("delete_member","Can delete/void TPA member"),("cancel_policy","Can cancel TPA policy"),
            ("approve_endorsement","Can approve TPA endorsement"),("process_endorsement","Can process TPA endorsement"),
            ("bypass_validation","Can bypass TPA validation"),("override_premium","Can override TPA premium"),
            ("view_sensitive_member_data","Can view sensitive TPA member data"),("view_ai_source_data","Can view TPA AI source data"),
            ("configure_tpa","Can configure TPA"),("export_tpa_data","Can export TPA data"),
        ]
    @property
    def display_reference(self):
        return self.ticket.reference

    def save(self,*args,**kwargs):
        new = self.pk is None
        with transaction.atomic():
            if new and not self.ticket_id:
                from .services.ticketing import create_parent_ticket
                self.ticket = create_parent_ticket(self)
            if new and not self.reference:
                self.reference = self.ticket.reference
            super().save(*args,**kwargs)
            if new:
                from .services.ticketing import record_transaction_link
                record_transaction_link(self)
    def __str__(self): return self.reference or "New transaction"

class MemberAction(TimeStampedModel):
    class Result(models.TextChoices):
        VALID="VALID","Valid"; WARNING="WARNING","Warning"; ERROR="ERROR","Error"; BYPASSED="BYPASSED","Bypassed"
    transaction=models.ForeignKey(MemberTransaction, related_name="member_actions", on_delete=models.CASCADE)
    member=models.ForeignKey(Member, null=True, blank=True, related_name="transaction_actions", on_delete=models.PROTECT)
    action=models.CharField(max_length=30)
    row_number=models.PositiveIntegerField(null=True, blank=True)
    submitted_data=models.JSONField(default=dict, blank=True)
    extracted_data=models.JSONField(default=dict, blank=True)
    corrected_data=models.JSONField(default=dict, blank=True)
    before_data=models.JSONField(default=dict, blank=True)
    after_data=models.JSONField(default=dict, blank=True)
    extraction_confidence=models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    validation_status=models.CharField(max_length=12, choices=Result.choices, default=Result.ERROR)
    validation_errors=models.JSONField(default=list, blank=True)
    warnings=models.JSONField(default=list, blank=True)
    calculated_premium=models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    calculation_snapshot=models.JSONField(default=dict, blank=True)
    card_number=models.CharField(max_length=100, blank=True)
    tpa_effective_date=models.DateField(null=True, blank=True)
    tpa_premium_amount=models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    tpa_override_reason=models.TextField(blank=True)
    processing_status=models.CharField(max_length=30, blank=True)
    processing_message=models.TextField(blank=True)
    processed_at=models.DateTimeField(null=True, blank=True)
    provenance=models.JSONField(default=list, blank=True)

class PolicyAccess(TimeStampedModel):
    organization=models.ForeignKey(Organization, related_name="policy_access", on_delete=models.CASCADE)
    policy=models.ForeignKey(Policy, related_name="access_entries", on_delete=models.CASCADE)
    user=models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="tpa_policy_access", on_delete=models.CASCADE)
    can_view=models.BooleanField(default=True)
    can_view_members=models.BooleanField(default=False)
    can_create_enrollment=models.BooleanField(default=False)
    can_create_endorsement=models.BooleanField(default=False)
    can_view_premium=models.BooleanField(default=False)
    can_approve=models.BooleanField(default=False)
    can_process=models.BooleanField(default=False)
    active=models.BooleanField(default=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["organization","policy","user"], name="tpa_unique_policy_access")]

class TransactionEvent(TimeStampedModel):
    transaction=models.ForeignKey(MemberTransaction, related_name="events", on_delete=models.CASCADE)
    actor=models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    event_type=models.CharField(max_length=50, db_index=True)
    summary=models.CharField(max_length=255)
    details=models.JSONField(default=dict, blank=True)
    class Meta: ordering=["created_at"]


class SourceDocument(TimeStampedModel):
    class State(models.TextChoices):
        RECEIVED="RECEIVED","Received"
        PROCESSING="PROCESSING","Processing"
        PROCESSED="PROCESSED","Processed"
        REVIEW="REVIEW","Needs review"
        FAILED="FAILED","Failed"
    transaction=models.ForeignKey(MemberTransaction, related_name="source_documents", on_delete=models.CASCADE)
    ticket_attachment=models.ForeignKey("tickets.TicketAttachment", null=True, blank=True, related_name="tpa_source_documents", on_delete=models.SET_NULL)
    file=models.FileField(upload_to="tpa/sources/%Y/%m/", blank=True)
    original_name=models.CharField(max_length=255)
    content_type=models.CharField(max_length=120, blank=True)
    size=models.PositiveIntegerField(default=0)
    document_kind=models.CharField(max_length=50, blank=True)
    extraction_method=models.CharField(max_length=50, blank=True)
    processing_state=models.CharField(max_length=20, choices=State.choices, default=State.RECEIVED, db_index=True)
    processed=models.BooleanField(default=False)
    processing_error=models.TextField(blank=True)
    extracted_payload=models.JSONField(default=dict, blank=True)
    extraction_confidence=models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ai_profile=models.ForeignKey("ai.AIExtractionProfile", null=True, blank=True, on_delete=models.SET_NULL)
    source_hash=models.CharField(max_length=64, blank=True, db_index=True)
    uploaded_by=models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

class TransactionQuery(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN="OPEN","Open"
        RESOLVED="RESOLVED","Resolved"
    class Purpose(models.TextChoices):
        APPROVAL="APPROVAL","Approval Query"
        TPA="TPA","TPA Query"
        CLIENT="CLIENT","Client Query"
    class Audience(models.TextChoices):
        CLIENT_VISIBLE="CLIENT_VISIBLE","Client Visible"
        INSURER_TPA_INTERNAL="INSURER_TPA_INTERNAL","Insurer / TPA Internal"
        SELECTED_PARTICIPANTS="SELECTED_PARTICIPANTS","Selected Participants"
    transaction=models.ForeignKey(MemberTransaction, related_name="queries", on_delete=models.CASCADE)
    ticket=models.OneToOneField(
        "tickets.Ticket",
        related_name="tpa_query",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    subject=models.CharField(max_length=255)
    purpose=models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.TPA, db_index=True)
    audience=models.CharField(max_length=30, choices=Audience.choices, default=Audience.CLIENT_VISIBLE, db_index=True)
    selected_participants=models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="selected_tpa_queries", blank=True)
    raised_by=models.ForeignKey(settings.AUTH_USER_MODEL, related_name="raised_tpa_queries", on_delete=models.PROTECT)
    pre_query_status=models.CharField(max_length=30, blank=True)
    status=models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    resolved_by=models.ForeignKey(settings.AUTH_USER_MODEL, related_name="resolved_tpa_queries", null=True, blank=True, on_delete=models.SET_NULL)
    resolved_at=models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering=["-created_at"]
    def __str__(self):
        return f"{self.transaction.reference} · {self.subject}"


class TransactionQueryMessage(TimeStampedModel):
    class Kind(models.TextChoices):
        QUERY="QUERY","Query"
        REPLY="REPLY","Reply"
        NOTE="NOTE","Note"
    query=models.ForeignKey(TransactionQuery, related_name="messages", on_delete=models.CASCADE)
    ticket_comment=models.OneToOneField("tickets.TicketComment", related_name="tpa_query_message", on_delete=models.CASCADE)
    sender=models.ForeignKey(settings.AUTH_USER_MODEL, related_name="tpa_query_messages", on_delete=models.PROTECT)
    kind=models.CharField(max_length=12, choices=Kind.choices, default=Kind.REPLY)
    audience=models.CharField(max_length=30, choices=TransactionQuery.Audience.choices, default=TransactionQuery.Audience.CLIENT_VISIBLE, db_index=True)
    shared_with_client_at=models.DateTimeField(null=True, blank=True)
    shared_with_client_by=models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="shared_tpa_query_messages", on_delete=models.SET_NULL)
    class Meta:
        ordering=["created_at"]


class InboundEmail(TimeStampedModel):
    def save(self, *args, **kwargs):
        if self.transaction_id and not self.ticket_id:
            self.ticket_id = self.transaction.ticket_id
            if kwargs.get('update_fields'):
                kwargs['update_fields'] = list(set(kwargs['update_fields']) | {'ticket'})
        return super().save(*args, **kwargs)

    class State(models.TextChoices):
        RECEIVED="RECEIVED","Received"
        PROCESSING="PROCESSING","Processing"
        REVIEW="REVIEW","Needs review"
        PROCESSED="PROCESSED","Processed"
        FAILED="FAILED","Failed"
        IGNORED="IGNORED","Not Endorsement / Ignored"
        UNAUTHORIZED="UNAUTHORIZED","Unauthorized Sender"
    provider=models.CharField(max_length=40, blank=True)
    created_by=models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="tpa_inbound_emails", on_delete=models.SET_NULL)
    provider_message_id=models.CharField(max_length=255)
    graph_message_id=models.CharField(max_length=255, blank=True, db_index=True)
    internet_message_id=models.CharField(max_length=500, blank=True, db_index=True)
    conversation_id=models.CharField(max_length=255, blank=True, db_index=True)
    mailbox=models.EmailField(blank=True, db_index=True)
    sender_name=models.CharField(max_length=255, blank=True)
    sender=models.EmailField()
    recipient=models.EmailField()
    to_addresses=models.JSONField(default=list, blank=True)
    cc_addresses=models.JSONField(default=list, blank=True)
    subject=models.CharField(max_length=500, blank=True)
    received_at=models.DateTimeField()
    body_text=models.TextField(blank=True)
    body_html=models.TextField(blank=True)
    source_hash=models.CharField(max_length=64, blank=True, db_index=True)
    attachment_metadata=models.JSONField(default=list, blank=True)
    processing_hints=models.JSONField(default=dict, blank=True)
    ai_extracted_payload=models.JSONField(default=dict, blank=True)
    raw_ai_output=models.JSONField(default=dict, blank=True)
    ai_provider_name=models.CharField(max_length=120, blank=True)
    ai_model_name=models.CharField(max_length=120, blank=True)
    ai_confidence=models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    classification=models.CharField(max_length=40, blank=True, db_index=True)
    classification_confidence=models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    processing_stage=models.CharField(max_length=50, blank=True)
    processing_state=models.CharField(max_length=20, choices=State.choices, default=State.RECEIVED, db_index=True)
    ticket=models.ForeignKey("tickets.Ticket", null=True, blank=True, on_delete=models.PROTECT, related_name="source_emails")
    transaction=models.ForeignKey(MemberTransaction, null=True, blank=True, related_name="source_emails", on_delete=models.SET_NULL)
    processing_error=models.TextField(blank=True)
    processed_at=models.DateTimeField(null=True, blank=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["provider","provider_message_id"], name="tpa_unique_inbound_email")]

class InboundEmailAttachment(TimeStampedModel):
    class State(models.TextChoices):
        RECEIVED="RECEIVED","Received"
        PROCESSING="PROCESSING","Processing"
        PROCESSED="PROCESSED","Processed"
        REVIEW="REVIEW","Needs review"
        FAILED="FAILED","Failed"
    inbound_email=models.ForeignKey(InboundEmail, related_name="attachments", on_delete=models.CASCADE)
    file=models.FileField(upload_to="tpa/inbound/%Y/%m/")
    original_name=models.CharField(max_length=255)
    content_type=models.CharField(max_length=120, blank=True)
    size=models.PositiveIntegerField(default=0)
    sha256=models.CharField(max_length=64, db_index=True)
    processing_state=models.CharField(max_length=20, choices=State.choices, default=State.RECEIVED, db_index=True)
    extracted_payload=models.JSONField(default=dict, blank=True)
    processing_error=models.TextField(blank=True)
    def __str__(self):
        return self.original_name

class TPAMailboxSyncState(TimeStampedModel):
    provider=models.CharField(max_length=40, default="office365_graph")
    mailbox=models.EmailField()
    folder=models.CharField(max_length=120, default="Inbox")
    delta_link=models.TextField(blank=True)
    last_attempted_at=models.DateTimeField(null=True, blank=True)
    last_successful_at=models.DateTimeField(null=True, blank=True)
    last_error=models.TextField(blank=True)
    messages_processed=models.PositiveIntegerField(default=0)
    messages_review=models.PositiveIntegerField(default=0)
    messages_ignored=models.PositiveIntegerField(default=0)
    messages_failed=models.PositiveIntegerField(default=0)
    scheduler_enabled=models.BooleanField(default=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["provider","mailbox","folder"], name="tpa_unique_mailbox_sync_state")]
    def __str__(self):
        return f"{self.provider} · {self.mailbox} · {self.folder}"


class TPAEmailAuthority(TimeStampedModel):
    email_address=models.EmailField(db_index=True)
    user=models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="tpa_email_authorities", on_delete=models.SET_NULL)
    organization=models.ForeignKey(Organization, related_name="email_authorities", on_delete=models.CASCADE)
    policy=models.ForeignKey(Policy, null=True, blank=True, related_name="email_authorities", on_delete=models.CASCADE)
    permitted_transaction_types=models.JSONField(default=list, blank=True)
    valid_from=models.DateField(null=True, blank=True)
    valid_until=models.DateField(null=True, blank=True)
    active=models.BooleanField(default=True, db_index=True)
    notes=models.TextField(blank=True)
    class Meta:
        constraints=[
            models.UniqueConstraint(fields=["email_address","organization","policy"], name="tpa_unique_email_authority")
        ]
        indexes=[models.Index(fields=["email_address","active"], name="tpa_email_a_email_a_4fd468_idx")]
    def __str__(self):
        scope=self.policy.policy_number if self.policy_id else self.organization.name_en
        return f"{self.email_address} · {scope}"


class ExtractionAttempt(TimeStampedModel):
    class Status(models.TextChoices):
        STARTED="STARTED","Started"
        SUCCESS="SUCCESS","Success"
        REVIEW="REVIEW","Needs Review"
        FAILED="FAILED","Failed"
    source_document=models.ForeignKey(SourceDocument, null=True, blank=True, related_name="extraction_attempts", on_delete=models.CASCADE)
    inbound_attachment=models.ForeignKey(InboundEmailAttachment, null=True, blank=True, related_name="extraction_attempts", on_delete=models.CASCADE)
    provider=models.ForeignKey("ai.AIProviderConfig", null=True, blank=True, related_name="tpa_extraction_attempts", on_delete=models.SET_NULL)
    stage=models.CharField(max_length=50)
    status=models.CharField(max_length=20, choices=Status.choices, default=Status.STARTED, db_index=True)
    model_name=models.CharField(max_length=120, blank=True)
    error=models.TextField(blank=True)
    raw_output=models.JSONField(default=dict, blank=True)
    metadata=models.JSONField(default=dict, blank=True)
    class Meta:
        ordering=["-created_at"]


class CardDispatch(TimeStampedModel):
    class Method(models.TextChoices):
        COURIER="COURIER","Courier"
        HAND_DELIVERY="HAND_DELIVERY","Hand Delivery"
        CLIENT_COLLECTION="CLIENT_COLLECTION","Collected by Client"
        INSURER_COLLECTION="INSURER_COLLECTION","Collected by Insurance Company"
        TPA_COLLECTION="TPA_COLLECTION","Collected from TPA"
        OTHER="OTHER","Other"
    class Status(models.TextChoices):
        PENDING="PENDING","Pending"
        READY="READY","Ready for Dispatch"
        DISPATCHED="DISPATCHED","Dispatched"
        IN_TRANSIT="IN_TRANSIT","In Transit"
        READY_COLLECTION="READY_COLLECTION","Ready for Collection"
        COLLECTED="COLLECTED","Collected"
        DELIVERED="DELIVERED","Delivered"
        FAILED="FAILED","Failed / Returned"
        NOT_REQUIRED="NOT_REQUIRED","Not Required"
    transaction=models.OneToOneField(MemberTransaction, related_name="card_dispatch", on_delete=models.CASCADE)
    method=models.CharField(max_length=30, choices=Method.choices, blank=True)
    status=models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING, db_index=True)
    courier_company=models.CharField(max_length=160, blank=True)
    tracking_number=models.CharField(max_length=120, blank=True, db_index=True)
    dispatched_at=models.DateTimeField(null=True, blank=True)
    expected_delivery_at=models.DateTimeField(null=True, blank=True)
    delivered_or_collected_at=models.DateTimeField(null=True, blank=True)
    recipient_name=models.CharField(max_length=160, blank=True)
    recipient_organization=models.CharField(max_length=180, blank=True)
    contact=models.CharField(max_length=100, blank=True)
    remarks=models.TextField(blank=True)
    proof_attachment=models.ForeignKey("tickets.TicketAttachment", null=True, blank=True, related_name="tpa_card_dispatch_proofs", on_delete=models.SET_NULL)
    recorded_by=models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="recorded_tpa_card_dispatches", on_delete=models.SET_NULL)
    def __str__(self):
        return f"{self.transaction.reference} · {self.get_status_display()}"

