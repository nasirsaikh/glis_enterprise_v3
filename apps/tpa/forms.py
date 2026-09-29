from django import forms
from django.db.models import Q
from django.utils import timezone

from apps.ai.models import AIProviderConfig

from .models import (
    BenefitPlan,
    CardDispatch,
    InboundEmail,
    Member,
    MemberTransaction,
    Policy,
    TPAOrganization,
    TransactionQuery,
)
from .services.access import visible_policies


class TransactionForm(forms.ModelForm):
    class Meta:
        model = MemberTransaction
        fields = ["policy", "transaction_type", "effective_date", "refund_basis", "remarks"]
        widgets = {
            "effective_date": forms.DateInput(
                attrs={"type": "date", "class": "input input-bordered input-sm w-full"}
            )
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields["policy"].queryset = (
                visible_policies(user)
                .filter(status=Policy.Status.ACTIVE)
                .filter(
                    Q(initial_enrollment_completed_at__isnull=False)
                    | Q(enrollments__enrollment_status="active")
                )
                .distinct()
            )
        else:
            self.fields["policy"].queryset = Policy.objects.none()
        self.fields["transaction_type"].choices = [
            choice
            for choice in MemberTransaction.Type.choices
            if choice[0] != MemberTransaction.Type.NEW_POLICY_ENROLLMENT
        ]
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class",
                "select select-bordered select-sm w-full"
                if isinstance(field.widget, forms.Select)
                else "input input-bordered input-sm w-full",
            )


    def clean(self):
        data = super().clean()
        tx_type = data.get("transaction_type")
        if tx_type in {
            MemberTransaction.Type.MEMBER_DELETE,
            MemberTransaction.Type.POLICY_CANCEL,
        }:
            if data.get("refund_basis") in {None, "", MemberTransaction.RefundBasis.NONE}:
                self.add_error(
                    "refund_basis",
                    "Choose Full Refund or Pro-Rata Refund for this endorsement.",
                )
        else:
            data["refund_basis"] = MemberTransaction.RefundBasis.NONE
        return data


class PolicyEnrollmentForm(forms.Form):
    sponsor = forms.ModelChoiceField(
        queryset=TPAOrganization.objects.none(),
        label="Individual / Corporate Sponsor",
    )
    insurance_company = forms.ModelChoiceField(
        queryset=TPAOrganization.objects.none(),
        label="Insurance Company",
    )
    tpa_organization = forms.ModelChoiceField(
        queryset=TPAOrganization.objects.none(),
        required=False,
        label="TPA",
    )
    policy_number = forms.CharField(max_length=80)
    policy_name = forms.CharField(max_length=180)
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    expiry_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    currency = forms.CharField(max_length=3, initial="OMR")
    stp_enabled = forms.BooleanField(required=False, initial=True)
    allowed_backdating_days = forms.IntegerField(min_value=0, max_value=3650, initial=30)

    plan_code = forms.CharField(max_length=50, initial="GOLD", label="Initial Plan Code")
    plan_name = forms.CharField(max_length=160, initial="Gold", label="Initial Plan Name")
    annual_premium = forms.DecimalField(
        max_digits=14,
        decimal_places=3,
        initial="0.000",
        label="Annual Premium",
    )
    default_sum_insured = forms.DecimalField(
        max_digits=16,
        decimal_places=3,
        required=False,
        label="Default Sum Insured",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sponsor"].queryset = TPAOrganization.objects.filter(
            organization_type__in=[
                TPAOrganization.Type.INDIVIDUAL,
                TPAOrganization.Type.CORPORATE,
            ],
            is_active=True,
        ).order_by("organization_type", "name_en")
        self.fields["insurance_company"].queryset = TPAOrganization.objects.filter(
            organization_type=TPAOrganization.Type.INSURER,
            is_active=True,
        ).order_by("name_en")
        self.fields["tpa_organization"].queryset = TPAOrganization.objects.filter(
            organization_type=TPAOrganization.Type.TPA,
            is_active=True,
        ).order_by("name_en")
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                css = "select select-bordered select-sm w-full"
            elif isinstance(field.widget, forms.CheckboxInput):
                css = "checkbox checkbox-primary checkbox-sm"
            else:
                css = "input input-bordered input-sm w-full"
            field.widget.attrs.setdefault("class", css)

    def clean_policy_number(self):
        value = self.cleaned_data["policy_number"].strip()
        if Policy.objects.filter(policy_number__iexact=value).exists():
            raise forms.ValidationError("A policy with this number already exists.")
        return value

    def clean(self):
        data = super().clean()
        start = data.get("start_date")
        end = data.get("expiry_date")
        if start and end and end < start:
            self.add_error("expiry_date", "Expiry date cannot be before start date.")
        return data


class BenefitPlanSetupForm(forms.ModelForm):
    class Meta:
        model = BenefitPlan
        fields = (
            "code",
            "name",
            "description",
            "annual_premium",
            "default_sum_insured",
            "is_active",
        )

    def __init__(self, *args, policy=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy = policy
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                css = "checkbox checkbox-primary checkbox-sm"
            else:
                css = "input input-bordered input-sm w-full"
            field.widget.attrs.setdefault("class", css)

    def clean_code(self):
        value = self.cleaned_data["code"].strip().upper()
        if self.policy and BenefitPlan.objects.filter(
            policy=self.policy,
            code__iexact=value,
        ).exists():
            raise forms.ValidationError("This plan code already exists for the policy.")
        return value


class MemberRowForm(forms.Form):
    employee_id = forms.CharField(required=False, label="Employee No.")
    first_name = forms.CharField(required=True)
    middle_name = forms.CharField(required=False)
    last_name = forms.CharField(required=True)
    date_of_birth = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    gender = forms.ChoiceField(
        choices=(("", "Select gender"), ("Male", "Male"), ("Female", "Female")),
        required=True,
    )
    relationship = forms.ChoiceField(
        choices=(("", "Select relationship"), *Member.Relationship.choices),
        required=True,
    )
    principal_reference = forms.ChoiceField(
        required=False,
        label="Parent Principal",
        choices=(("", "Select principal member"),),
        help_text="Required for spouse, child and other dependents.",
    )
    plan_code = forms.ChoiceField(required=True, label="Benefit plan")
    national_id = forms.CharField(required=False, label="Civil / National ID")
    passport_number = forms.CharField(required=False)

    def __init__(self, *args, transaction=None, current_action=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.transaction = transaction
        self.current_action = current_action

        plans = transaction.policy.plans.filter(is_active=True).order_by("code") if transaction else []
        self.fields["plan_code"].choices = [
            ("", "Select benefit plan"),
            *[(plan.code, f"{plan.code} · {plan.name}") for plan in plans],
        ]

        principal_choices = [("", "Select principal member")]
        if transaction:
            active_principals = (
                Member.objects.filter(
                    relationship=Member.Relationship.PRINCIPAL,
                    status=Member.Status.ACTIVE,
                    enrollments__policy=transaction.policy,
                    enrollments__enrollment_status="active",
                )
                .distinct()
                .order_by("first_name", "last_name", "pk")
            )
            principal_choices.extend(
                (
                    f"member:{member.pk}",
                    f"{member.tpa_member_id} · {member.full_name}"
                    + (f" · {member.employee_id}" if member.employee_id else ""),
                )
                for member in active_principals
            )

            for action in transaction.member_actions.all().order_by("row_number", "pk"):
                data = {
                    **(action.submitted_data or {}),
                    **(action.extracted_data or {}),
                    **(action.corrected_data or {}),
                }
                if str(data.get("relationship") or "").upper() != Member.Relationship.PRINCIPAL:
                    continue
                full_name = " ".join(
                    value for value in [
                        str(data.get("first_name") or "").strip(),
                        str(data.get("middle_name") or "").strip(),
                        str(data.get("last_name") or "").strip(),
                    ] if value
                ) or f"Principal row {action.row_number or action.pk}"
                employee_id = str(data.get("employee_id") or "").strip()
                label = f"Current transaction · {full_name}"
                if employee_id:
                    label += f" · {employee_id}"
                principal_choices.append((f"action:{action.pk}", label))

        self.fields["principal_reference"].choices = principal_choices

        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class",
                "select select-bordered select-sm w-full"
                if isinstance(field.widget, forms.Select)
                else "input input-bordered input-sm w-full",
            )

    def clean(self):
        data = super().clean()
        relationship = data.get("relationship")
        reference = data.get("principal_reference") or ""

        data["principal_member_id"] = ""
        data["principal_action_id"] = ""
        data["principal_employee_id"] = ""

        if relationship == Member.Relationship.PRINCIPAL:
            data["principal_reference"] = ""
            return data

        if relationship and not reference:
            self.add_error(
                "principal_reference",
                "Select the parent principal for a spouse, child or other dependent.",
            )
            return data

        if reference.startswith("member:"):
            data["principal_member_id"] = reference.split(":", 1)[1]
        elif reference.startswith("action:"):
            data["principal_action_id"] = reference.split(":", 1)[1]

        if self.transaction:
            active = MemberPolicyEnrollment.objects.filter(
                policy=self.transaction.policy,
                enrollment_status=MemberPolicyEnrollment.Status.ACTIVE,
            )
            duplicate_checks = (
                ("employee_id", "member__employee_id", "Employee number"),
                ("national_id", "member__national_id", "Civil/National ID"),
                ("passport_number", "member__passport_number", "Passport number"),
            )
            for field_name, lookup, label in duplicate_checks:
                value = str(data.get(field_name) or "").strip()
                if not value:
                    continue
                if active.filter(**{f"{lookup}__iexact": value}).exists():
                    self.add_error(
                        field_name,
                        f"{label} is already active under this policy.",
                    )
                    continue

                rows = self.transaction.member_actions.all()
                if self.current_action is not None and self.current_action.pk:
                    rows = rows.exclude(pk=self.current_action.pk)
                for action in rows:
                    row = {
                        **(action.submitted_data or {}),
                        **(action.extracted_data or {}),
                        **(action.corrected_data or {}),
                    }
                    if str(row.get(field_name) or "").strip().casefold() == value.casefold():
                        self.add_error(
                            field_name,
                            f"{label} already exists in this endorsement.",
                        )
                        break

        return data


class MemberLookupRowForm(forms.Form):
    tpa_member_id = forms.CharField(required=False, label="TPA Member ID")
    card_number = forms.CharField(required=False, label="Card / Member Number")
    employee_id = forms.CharField(required=False, label="Employee No.")
    national_id = forms.CharField(required=False, label="Civil / National ID")
    passport_number = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "input input-bordered input-sm w-full")

    def clean(self):
        data = super().clean()
        if not any(data.get(name) for name in self.fields):
            raise forms.ValidationError("Provide at least one member identifier.")
        return data


class MemberUploadForm(forms.Form):
    member_file = forms.FileField(
        label="Member file",
        help_text="CSV or XLSX, maximum 5 MB.",
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".csv,.xlsx",
                "class": "file-input file-input-bordered file-input-sm w-full",
            }
        ),
    )



class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(item, initial) for item in data]
        return [single_clean(data, initial)] if data else []


class InboundEmailForm(forms.ModelForm):
    ai_provider = forms.ModelChoiceField(
        queryset=AIProviderConfig.objects.none(),
        required=False,
        label="AI Provider",
        help_text="Optional. Leave blank to use the highest-priority eligible email extraction provider.",
    )
    policy = forms.ModelChoiceField(
        queryset=Policy.objects.none(),
        required=False,
        help_text="Optional policy hint. AI will try to identify it when left blank.",
    )
    transaction_type = forms.ChoiceField(
        required=False,
        choices=(
            ("", "Let AI identify"),
            *[
                choice
                for choice in MemberTransaction.Type.choices
                if choice[0] != MemberTransaction.Type.NEW_POLICY_ENROLLMENT
            ],
        ),
        help_text="Optional endorsement type hint. Initial policy enrollment is created from its dedicated setup page.",
    )
    effective_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Optional effective-date hint.",
    )
    attachments = MultipleFileField(
        required=False,
        label="Email attachments",
        widget=MultipleFileInput(
            attrs={
                "multiple": True,
                "accept": ".csv,.xlsx,.xls,.jpg,.jpeg,.png,.webp,.pdf",
            }
        ),
        help_text="CSV/XLSX/XLS are parsed directly. PDF and image evidence use text extraction/OCR plus AI field mapping when required.",
    )
    process_with_ai = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Immediately extract the email and create the TPA transaction.",
    )

    class Meta:
        model = InboundEmail
        fields = [
            "provider",
            "provider_message_id",
            "sender",
            "recipient",
            "subject",
            "received_at",
            "body_text",
        ]
        widgets = {
            "received_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}
            ),
            "body_text": forms.Textarea(
                attrs={"rows": 12}
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["policy"].queryset = (
            visible_policies(user).filter(status=Policy.Status.ACTIVE)
            if user
            else Policy.objects.none()
        )
        eligible_provider_ids = [
            provider.pk
            for provider in AIProviderConfig.objects.filter(
                is_active=True,
                allow_sensitive_data=True,
            ).order_by("priority", "id")
            if "email_extraction"
            in {
                str(item).strip().lower()
                for item in (provider.task_capabilities or [])
            }
        ]
        self.fields["ai_provider"].queryset = AIProviderConfig.objects.filter(
            pk__in=eligible_provider_ids
        ).order_by("priority", "id")
        if not self.is_bound:
            self.fields["received_at"].initial = timezone.localtime().replace(
                second=0,
                microsecond=0,
            )
        self.fields["provider"].initial = "manual"
        self.fields["provider_message_id"].required = False
        self.fields["provider_message_id"].help_text = (
            "Optional for manual entry; a unique message ID is generated automatically."
        )
        for field in self.fields.values():
            if isinstance(field.widget, forms.Textarea):
                css = "textarea textarea-bordered textarea-sm w-full"
            elif isinstance(field.widget, forms.Select):
                css = "select select-bordered select-sm w-full"
            elif isinstance(field.widget, forms.ClearableFileInput):
                css = "file-input file-input-bordered file-input-sm w-full"
            elif isinstance(field.widget, forms.CheckboxInput):
                css = "checkbox checkbox-primary checkbox-sm"
            else:
                css = "input input-bordered input-sm w-full"
            field.widget.attrs.setdefault("class", css)

    def clean_attachments(self):
        files = self.cleaned_data.get("attachments") or []
        allowed = {
            ".csv",
            ".xlsx",
            ".xls",
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".pdf",
        }
        for uploaded in files:
            name = (uploaded.name or "").lower()
            suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
            if suffix not in allowed:
                raise forms.ValidationError(
                    f"Unsupported attachment type: {uploaded.name}"
                )
            if uploaded.size > 10 * 1024 * 1024:
                raise forms.ValidationError(
                    f"{uploaded.name} exceeds the 10 MB attachment limit."
                )
        return files



class SourceBundleUploadForm(forms.Form):
    source_files = MultipleFileField(
        label="Source documents",
        required=True,
        widget=MultipleFileInput(
            attrs={
                "multiple": True,
                "accept": ".eml,.csv,.xlsx,.xls,.pdf,.png,.jpg,.jpeg,.webp",
                "class": "file-input file-input-bordered file-input-sm w-full",
            }
        ),
        help_text="Upload EML, Excel/CSV, PDF, passport/ID images or multiple front/back evidence files.",
    )

    def clean_source_files(self):
        files = self.cleaned_data.get("source_files") or []
        if len(files) > 20:
            raise forms.ValidationError("Upload a maximum of 20 source files at one time.")
        allowed = {".eml", ".csv", ".xlsx", ".xls", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}
        for uploaded in files:
            suffix = "." + uploaded.name.lower().rsplit(".", 1)[-1] if "." in uploaded.name else ""
            if suffix not in allowed:
                raise forms.ValidationError(f"Unsupported source file: {uploaded.name}")
            if uploaded.size > 10 * 1024 * 1024:
                raise forms.ValidationError(f"{uploaded.name} exceeds 10 MB.")
        return files


class QueryRaiseForm(forms.Form):
    subject = forms.CharField(max_length=255)
    purpose = forms.ChoiceField(
        choices=TransactionQuery.Purpose.choices,
        initial=TransactionQuery.Purpose.TPA,
    )
    audience = forms.ChoiceField(
        choices=TransactionQuery.Audience.choices,
        initial=TransactionQuery.Audience.CLIENT_VISIBLE,
    )
    message = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "textarea textarea-bordered textarea-sm w-full richtext-source",
            }
        )
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.setdefault(
                "class",
                "select select-bordered select-sm w-full"
                if isinstance(field.widget, forms.Select)
                else "textarea textarea-bordered textarea-sm w-full"
                if isinstance(field.widget, forms.Textarea)
                else "input input-bordered input-sm w-full",
            )


class QueryMessageForm(forms.Form):
    message = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "textarea textarea-bordered textarea-sm w-full richtext-source",
            }
        )
    )
    audience = forms.ChoiceField(
        choices=TransactionQuery.Audience.choices,
        required=False,
    )
    attachments = MultipleFileField(
        required=False,
        widget=MultipleFileInput(
            attrs={
                "multiple": True,
                "accept": ".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx",
                "class": "file-input file-input-bordered file-input-sm w-full",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["message"].widget.attrs.setdefault(
            "class", "textarea textarea-bordered textarea-sm w-full richtext-source"
        )
        self.fields["audience"].widget.attrs.setdefault(
            "class", "select select-bordered select-sm w-full"
        )


class BulkCardSelectionForm(forms.Form):
    card_numbers = forms.CharField(
        label="Paste Card Numbers",
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "class": "textarea textarea-bordered w-full",
                "placeholder": "CARD-001\nCARD-002, CARD-003",
            }
        ),
    )


class CardDispatchForm(forms.ModelForm):
    class Meta:
        model = CardDispatch
        fields = [
            "method",
            "status",
            "courier_company",
            "tracking_number",
            "dispatched_at",
            "expected_delivery_at",
            "delivered_or_collected_at",
            "recipient_name",
            "recipient_organization",
            "contact",
            "remarks",
        ]
        widgets = {
            "dispatched_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "expected_delivery_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "delivered_or_collected_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "remarks": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                css = "select select-bordered select-sm w-full"
            elif isinstance(field.widget, forms.Textarea):
                css = "textarea textarea-bordered textarea-sm w-full"
            else:
                css = "input input-bordered input-sm w-full"
            field.widget.attrs.setdefault("class", css)


class TPAProcessingRowForm(forms.Form):
    card_number = forms.CharField(required=False, max_length=100)
    effective_date = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    amount = forms.DecimalField(max_digits=14, decimal_places=3, required=True)
    override_reason = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    comments = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Textarea):
                css = "textarea textarea-bordered textarea-sm w-full"
            elif isinstance(field.widget, forms.Select):
                css = "select select-bordered select-sm w-full"
            else:
                css = "input input-bordered input-sm w-full"
            field.widget.attrs.setdefault("class", css)
