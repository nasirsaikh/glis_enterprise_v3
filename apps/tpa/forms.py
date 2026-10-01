from apps.accounts.models import Organization
from django import forms
from django.forms import BaseFormSet, formset_factory
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from apps.ai.models import AIExtractionProfile, AIProviderConfig, AITrainingExample
from apps.core.models import SiteSettings
from apps.tickets.models import Product
from apps.tickets.services.access import accessible_products

from .models import (
    BenefitPlan,
    CardDispatch,
    InboundEmail,
    Member,
    MemberPolicyEnrollment,
    MemberTransaction,
    Policy,

    TransactionQuery,
)
from .services.access import visible_policies
from services.tenancy import organization_ids, visible_users


class TransactionForm(forms.ModelForm):
    class Meta:
        model = MemberTransaction
        fields = [
            "policy",
            "transaction_type",
            "effective_date",
            "refund_basis",
            "expected_reactivation_date",
            "remarks",
        ]
        widgets = {
            "effective_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control form-control-sm w-100"}
            ),
            "expected_reactivation_date": forms.DateInput(
                attrs={"type": "date", "class": "form-control form-control-sm w-100"}
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user=user
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
        tx_type = (
            self.data.get("transaction_type")
            if self.is_bound
            else getattr(self.instance, "transaction_type", "")
        )
        self.fields["remarks"].label = "Reason / Remarks"
        self.fields["expected_reactivation_date"].label = (
            "Expected Reactivation Date (Temporary Suspension only)"
        )
        self.fields["expected_reactivation_date"].help_text = (
            "Optional. Used only for Temporary Suspension; ignored for other endorsement types."
        )
        if tx_type == MemberTransaction.Type.MEMBER_SUSPEND:
            self.fields["remarks"].label = "Suspension Reason"
            self.fields["remarks"].required = True
        elif tx_type == MemberTransaction.Type.MEMBER_TERMINATE:
            self.fields["remarks"].label = "Termination Reason"
        elif tx_type == MemberTransaction.Type.POLICY_CANCEL:
            self.fields["remarks"].label = "Cancellation Reason"
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class",
                "form-select form-select-sm w-100"
                if isinstance(field.widget, forms.Select)
                else "form-control form-control-sm w-100",
            )


    def clean(self):
        data = super().clean()
        tx_type = data.get("transaction_type")
        if data.get('policy') and tx_type and not self.instance.pk:
            from .services.access import can_create_for_policy
            if not can_create_for_policy(self.user,data['policy'],tx_type):self.add_error('policy','Creation permission is required for this policy.')

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

        if tx_type != MemberTransaction.Type.MEMBER_SUSPEND:
            data["expected_reactivation_date"] = None
        elif (
            data.get("expected_reactivation_date")
            and data.get("effective_date")
            and data["expected_reactivation_date"] < data["effective_date"]
        ):
            self.add_error(
                "expected_reactivation_date",
                "Expected reactivation date cannot be before the suspension effective date.",
            )
        return data


class TransactionDetailsForm(TransactionForm):
    """An existing workflow keeps its policy and member-row semantics."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["policy"].queryset = Policy.objects.filter(pk=self.instance.policy_id)
        self.fields["policy"].disabled = True
        self.fields["policy"].help_text = "The policy is fixed for this request."
        if (self.instance.transaction_type == MemberTransaction.Type.NEW_POLICY_ENROLLMENT
                or self.instance.member_actions.exists()):
            self.fields["transaction_type"].choices = [
                (self.instance.transaction_type, self.instance.get_transaction_type_display())
            ]
            self.fields["transaction_type"].disabled = True
            self.fields["transaction_type"].help_text = "Remove draft member rows before changing the endorsement type."
        self.fields["remarks"].widget = forms.Textarea(attrs={"class": "form-control w-100", "rows": 4})


PROMPT_TASKS = [AIExtractionProfile.Task.EMAIL_EXTRACTION, AIExtractionProfile.Task.MEMBER_FIELD_MAPPING]


class ExtractionPromptForm(forms.ModelForm):
    class Meta:
        model = AIExtractionProfile
        fields = ["name", "task", "applicable_product", "applicable_transaction_type", "system_prompt",
                  "instructions", "field_aliases", "priority", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["task"].choices = [choice for choice in AIExtractionProfile.Task.choices if choice[0] in PROMPT_TASKS]
        self.fields["applicable_transaction_type"] = forms.ChoiceField(
            choices=[("", "All endorsement types"), *MemberTransaction.Type.choices], required=False,
            initial=self.instance.applicable_transaction_type,
        )
        self.fields["applicable_product"].help_text = "Leave blank for all products, or use the policy product code (for example MEDICAL)."
        self.fields["field_aliases"].help_text = 'Canonical field to source labels, for example {"national_id": ["Civil No", "CPR"]}.'
        self.fields["priority"].help_text = "Lower numbers run first among equally specific profiles. Edit an existing active profile to change its extraction instructions."
        for field in self.fields.values():
            field.widget.attrs["class"] = ("form-check-input glis-switch" if isinstance(field.widget, forms.CheckboxInput)
                else "form-control w-100" if isinstance(field.widget, forms.Textarea)
                else "form-select w-100" if isinstance(field.widget, forms.Select)
                else "form-control w-100")
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs["rows"] = 5

    def clean_field_aliases(self):
        from .services.extraction import CANONICAL_MEMBER_FIELDS, EMAIL_FIELDS
        aliases = self.cleaned_data.get("field_aliases") or {}
        if not isinstance(aliases, dict):
            raise forms.ValidationError("Field aliases must be a JSON object.")
        for key, values in aliases.items():
            if key not in (*CANONICAL_MEMBER_FIELDS, *EMAIL_FIELDS):
                raise forms.ValidationError(f"Unknown canonical member field: {key}.")
            if not isinstance(values, (list, str)) or (isinstance(values, list) and not all(isinstance(v, str) for v in values)):
                raise forms.ValidationError("Each field must have a source label or list of source labels.")
        return aliases


class PromptExampleForm(forms.ModelForm):
    class Meta:
        model = AITrainingExample
        fields = ["name", "input_text", "expected_output", "sort_order", "is_active"]
        widgets = {"input_text": forms.Textarea(attrs={"rows": 5}), "expected_output": forms.Textarea(attrs={"rows": 7})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = ("form-check-input glis-switch" if isinstance(field.widget, forms.CheckboxInput)
                else "form-control w-100" if isinstance(field.widget, forms.Textarea)
                else "form-control w-100")

    def clean_expected_output(self):
        from .services.extraction import normalize_ai_payload
        value = self.cleaned_data["expected_output"]
        try:
            normalize_ai_payload(value)
        except (ValueError, TypeError):
            raise forms.ValidationError('Expected output must be an object with a "members" array of objects.')
        return value


class PromptPreviewForm(forms.Form):
    sample_text = forms.CharField(max_length=30000, label="Sample email body or OCR text",
                                 widget=forms.Textarea(attrs={"rows": 7, "class": "form-control w-100"}))


class PolicyEnrollmentForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.none(), required=False)
    policy_type = forms.ChoiceField(choices=[], required=False)

    organization = forms.ModelChoiceField(
        queryset=Organization.objects.none(),
        label="Organization",
        help_text="Organizations are assigned globally to your user account.",
    )
    insurance_company = forms.ModelChoiceField(
        queryset=Organization.objects.none(),
        label="Insurance Company",
    )
    policy_number = forms.CharField(max_length=80)
    policy_name = forms.CharField(max_length=180)
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    expiry_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    currency = forms.CharField(max_length=3, initial="OMR")
    stp_enabled = forms.BooleanField(required=False, initial=True)
    allowed_backdating_days = forms.IntegerField(min_value=0, max_value=3650, initial=30)

    # Legacy single-plan fields are retained for backward-compatible POSTs.
    # The current browser UI uses InitialBenefitPlanFormSet instead.
    plan_code = forms.CharField(max_length=50, required=False, widget=forms.HiddenInput())
    plan_name = forms.CharField(max_length=160, required=False, widget=forms.HiddenInput())
    annual_premium = forms.DecimalField(max_digits=14, decimal_places=3, required=False, widget=forms.HiddenInput())
    default_sum_insured = forms.DecimalField(max_digits=16, decimal_places=3, required=False, widget=forms.HiddenInput())

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

        organization_qs = Organization.objects.filter(
            is_active=True,
        ).order_by("organization_type", "name_en")

        if not user or not user.is_authenticated:
            organization_qs = organization_qs.none()
        elif not user.is_superuser:
            organization_qs = organization_qs.filter(pk__in=organization_ids(user))

        products = accessible_products(user).filter(project__workflow_type='NEW_POLICY_ENROLLMENT') if user else Product.objects.none()
        self.fields['product'].queryset = products
        value = self.data.get('product') or self.initial.get('product')
        product = products.filter(pk=value).first() if str(value or '').isdigit() else products.first()
        if product:
            self.fields['product'].initial = product
            self.fields['policy_type'].choices = [(v.get('code'),v.get('name',v.get('code'))) if isinstance(v,dict) else (v,str(v).replace('_',' ').title()) for v in product.policy_types]
            if self.fields['policy_type'].choices:
                self.fields['policy_type'].initial = self.fields['policy_type'].choices[0][0]
        self.fields['product'].widget.attrs.update({'hx-get':'/portal/tpa/policy-enrollment/new/','hx-target':'#policy-enrollment-wizard','hx-include':'closest form','hx-trigger':'change'})
        self.fields["organization"].queryset = organization_qs
        if organization_qs.count() == 1:
            only_organization = organization_qs.first()
            self.fields["organization"].initial = only_organization
            self.fields["organization"].disabled = True
            self.fields["organization"].help_text = (
                "Your only assigned organization is selected automatically."
            )
        elif organization_qs.exists():
            self.fields["organization"].help_text = (
                "Select one of the organizations assigned to your user account."
            )
        else:
            self.fields["organization"].help_text = (
                "No eligible organization is assigned to your user account. "
                "Ask an administrator to update your user organizations."
            )

        self.fields["insurance_company"].queryset = Organization.objects.filter(
            organization_type=Organization.Type.INSURER,
            is_active=True,
        ).order_by("name_en")


        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                css = "form-select form-select-sm w-100"
            elif isinstance(field.widget, forms.CheckboxInput):
                css = "form-check-input"
            else:
                css = "form-control form-control-sm w-100"
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

        data['product'] = data.get('product') or self.fields['product'].queryset.first()
        choices = self.fields['policy_type'].choices
        data['policy_type'] = data.get('policy_type') or (choices[0][0] if choices else 'GROUP_MEDICAL')
        organization = data.get("organization")
        profile = getattr(self.user, "profile", None) if self.user else None
        if organization and profile is not None and profile.organizations.exists():
            if not profile.organizations.filter(pk=organization.pk, is_active=True).exists():
                self.add_error(
                    "organization",
                    "You can create enrollments only for organizations assigned to your user account.",
                )
        return data


class BenefitPlanSetupForm(forms.ModelForm):
    class Meta:
        model = BenefitPlan
        fields = (
            "code",
            "name",
            "annual_premium",
            "default_sum_insured",
            "is_active",
        )

    def __init__(self, *args, policy=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.policy = policy
        if not self.is_bound and not getattr(self.instance, "pk", None):
            self.fields["is_active"].initial = True
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                css = "form-check-input"
            elif isinstance(field.widget, forms.Textarea):
                css = "form-control form-control-sm w-100"
            else:
                css = "form-control form-control-sm w-100"
            field.widget.attrs.setdefault("class", css)

    def clean_code(self):
        value = self.cleaned_data["code"].strip().upper()
        if self.policy and BenefitPlan.objects.filter(
            policy=self.policy,
            code__iexact=value,
        ).exists():
            raise forms.ValidationError("This plan code already exists for the policy.")
        return value


class InitialBenefitPlanFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        seen = set()
        populated = 0
        for form in self.forms:
            data = getattr(form, "cleaned_data", {}) or {}
            if data.get("DELETE"):
                continue
            code = str(data.get("code") or "").strip().upper()
            name = str(data.get("name") or "").strip()
            if not code and not name:
                continue
            populated += 1
            if code in seen:
                form.add_error("code", "Benefit plan codes must be unique within the policy.")
            seen.add(code)
        if populated < 1:
            raise forms.ValidationError("Add at least one benefit plan.")


InitialBenefitPlanFormSet = formset_factory(
    BenefitPlanSetupForm,
    formset=InitialBenefitPlanFormSet,
    extra=0,
    can_delete=True,
    max_num=20,
    validate_max=True,
)


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
                "form-select form-select-sm w-100"
                if isinstance(field.widget, forms.Select)
                else "form-control form-control-sm w-100",
            )

    def clean(self):
        data = super().clean()
        relationship = data.get("relationship")
        reference = data.get("principal_reference") or ""

        data["principal_member_id"] = ""
        data["principal_action_id"] = ""
        data["principal_employee_id"] = ""

        # Manual intake must reject duplicates before a MemberAction is created.
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
            field.widget.attrs.setdefault("class", "form-control form-control-sm w-100")

    def clean(self):
        data = super().clean()
        if not any(data.get(name) for name in self.fields):
            raise forms.ValidationError("Provide at least one member identifier.")
        return data


class MemberDemographicUpdateForm(MemberLookupRowForm):
    first_name = forms.CharField(required=True)
    middle_name = forms.CharField(required=False)
    last_name = forms.CharField(required=True)
    date_of_birth = forms.DateField(required=True, widget=forms.DateInput(attrs={"type": "date"}))
    gender = forms.ChoiceField(
        choices=(("", "Select gender"), ("Male", "Male"), ("Female", "Female")),
        required=True,
    )
    employee_id = forms.CharField(required=False, label="Employee No.")
    national_id = forms.CharField(required=False, label="Civil / National ID")
    passport_number = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tpa_member_id"].widget = forms.HiddenInput()
        self.fields["card_number"].widget = forms.HiddenInput()
        for field in self.fields.values():
            if isinstance(field.widget, forms.HiddenInput):
                continue
            field.widget.attrs["class"] = (
                "form-select form-select-sm w-100"
                if isinstance(field.widget, forms.Select)
                else "form-control form-control-sm w-100"
            )


class MemberUploadForm(forms.Form):
    member_file = forms.FileField(
        label="Member file",
        help_text="CSV or XLSX, maximum 5 MB.",
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".csv,.xlsx",
                "class": "form-control form-control-sm w-100",
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
                attrs={"rows": 4}
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
                supports_vision=False,
            ).exclude(model_name__icontains="glm-ocr").order_by("priority", "id")
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
                css = "form-control form-control-sm w-100"
            elif isinstance(field.widget, forms.Select):
                css = "form-select form-select-sm w-100"
            elif isinstance(field.widget, forms.ClearableFileInput):
                css = "form-control form-control-sm w-100"
            elif isinstance(field.widget, forms.CheckboxInput):
                css = "form-check-input"
            else:
                css = "form-control form-control-sm w-100"
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
                "accept": ".eml,.msg,.csv,.xlsx,.xls,.pdf,.png,.jpg,.jpeg,.webp",
                "class": "form-control form-control-sm w-100",
            }
        ),
        help_text="Upload EML/Outlook MSG, Excel/CSV, PDF, passport/ID images or multiple front/back evidence files.",
    )

    def clean_source_files(self):
        files = self.cleaned_data.get("source_files") or []
        if len(files) > 20:
            raise forms.ValidationError("Upload a maximum of 20 source files at one time.")
        allowed = {".eml", ".msg", ".csv", ".xlsx", ".xls", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}
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
    selected_participants = forms.ModelMultipleChoiceField(
        queryset=get_user_model().objects.none(),
        required=False,
        label="Selected participants",
        widget=forms.SelectMultiple(
            attrs={"class": "form-select form-select-sm w-100", "size": 5}
        ),
    )
    message = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "form-control form-control-sm w-100 richtext-source",
            }
        )
    )
    attachments = MultipleFileField(
        required=False,
        widget=MultipleFileInput(
            attrs={
                "multiple": True,
                "accept": ".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx,.csv",
                "class": "form-control form-control-sm w-100",
            }
        ),
    )

    def __init__(self, *args, transaction=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.transaction = transaction
        if transaction is not None:
            scope = (
                Q(pk=transaction.requester_id)
                | Q(tpa_policy_access__policy=transaction.policy,
                    tpa_policy_access__active=True, tpa_policy_access__can_view=True)
            )
            if transaction.ticket_id:
                scope |= Q(support_groups__in=transaction.ticket.groups.all())
                scope |= Q(managed_support_groups__in=transaction.ticket.groups.all())
            self.fields["selected_participants"].queryset = visible_users(user).filter(scope).distinct().order_by(
                "first_name", "last_name", "email", "username"
            )
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class",
                "form-select form-select-sm w-100"
                if isinstance(field.widget, (forms.Select, forms.SelectMultiple))
                else "form-control form-control-sm w-100"
                if isinstance(field.widget, forms.ClearableFileInput)
                else "form-control form-control-sm w-100"
                if isinstance(field.widget, forms.Textarea)
                else "form-control form-control-sm w-100",
            )

    def clean(self):
        data = super().clean()
        if (
            data.get("audience") == TransactionQuery.Audience.SELECTED_PARTICIPANTS
            and not data.get("selected_participants")
        ):
            self.add_error(
                "selected_participants",
                "Select at least one participant for a restricted conversation.",
            )
        return data


class QueryMessageForm(forms.Form):
    message = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "class": "form-control form-control-sm w-100 richtext-source",
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
                "class": "form-control form-control-sm w-100",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["message"].widget.attrs.setdefault(
            "class", "form-control form-control-sm w-100 richtext-source"
        )
        self.fields["audience"].widget.attrs.setdefault(
            "class", "form-select form-select-sm w-100"
        )


class BulkCardSelectionForm(forms.Form):
    card_numbers = forms.CharField(
        label="Paste Card Numbers",
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "class": "form-control w-100",
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
                css = "form-select form-select-sm w-100"
            elif isinstance(field.widget, forms.Textarea):
                css = "form-control form-control-sm w-100"
            else:
                css = "form-control form-control-sm w-100"
            field.widget.attrs.setdefault("class", css)


class TransactionRejectionForm(forms.Form):
    reason = forms.CharField(
        label="Rejection reason",
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-control w-100"}),
    )


class TPABulkProcessingForm(forms.Form):
    file = forms.FileField(label="Completed member file", widget=forms.ClearableFileInput(
        attrs={"accept": ".xlsx,.csv", "class": "form-control form-control-sm w-100"}
    ))


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
                css = "form-control form-control-sm w-100"
            elif isinstance(field.widget, forms.Select):
                css = "form-select form-select-sm w-100"
            else:
                css = "form-control form-control-sm w-100"
            field.widget.attrs.setdefault("class", css)


class PolicyDetailsForm(forms.ModelForm):
    class Meta:
        model = Policy
        fields = ("policy_number", "policy_name", "start_date", "expiry_date", "currency",
                  "stp_enabled", "allowed_backdating_days")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "form-check-input" if isinstance(field.widget, forms.CheckboxInput)
                else "form-control form-control-sm w-100"
            )

    def clean_policy_number(self):
        value = self.cleaned_data["policy_number"].strip()
        if Policy.objects.filter(policy_number__iexact=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("A policy with this number already exists.")
        return value

    def clean_currency(self):
        value = self.cleaned_data["currency"].strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise forms.ValidationError("Use a three-letter currency code.")
        return value
