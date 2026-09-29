from django import forms
from django.utils import timezone

from .models import InboundEmail, Member, MemberTransaction, Policy
from .services.access import visible_policies


class TransactionForm(forms.ModelForm):
    class Meta:
        model = MemberTransaction
        fields = ["policy", "transaction_type", "effective_date", "remarks"]
        widgets = {
            "effective_date": forms.DateInput(
                attrs={"type": "date", "class": "tw:d-input tw:d-input-bordered tw:w-full"}
            )
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["policy"].queryset = visible_policies(user) if user else Policy.objects.none()
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class",
                "tw:d-select tw:d-select-bordered tw:w-full"
                if isinstance(field.widget, forms.Select)
                else "tw:d-input tw:d-input-bordered tw:w-full",
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

    def __init__(self, *args, transaction=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.transaction = transaction

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
                "tw:d-select tw:d-select-bordered tw:w-full"
                if isinstance(field.widget, forms.Select)
                else "tw:d-input tw:d-input-bordered tw:w-full",
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

        return data


class MemberLookupRowForm(forms.Form):
    tpa_member_id = forms.CharField(required=False, label="TPA Member ID")
    employee_id = forms.CharField(required=False, label="Employee No.")
    national_id = forms.CharField(required=False, label="Civil / National ID")
    passport_number = forms.CharField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "tw:d-input tw:d-input-bordered tw:w-full")

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
                "class": "tw:file-input tw:file-input-bordered tw:w-full",
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
    policy = forms.ModelChoiceField(
        queryset=Policy.objects.none(),
        required=False,
        help_text="Optional policy hint. AI will try to identify it when left blank.",
    )
    transaction_type = forms.ChoiceField(
        required=False,
        choices=(("", "Let AI identify"), *MemberTransaction.Type.choices),
        help_text="Optional transaction type hint.",
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
                "accept": ".csv,.xlsx,.jpg,.jpeg,.png,.webp,.pdf",
            }
        ),
        help_text="CSV/XLSX are imported directly. Images use a vision AI provider. PDF is retained for review.",
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
                css = "tw:d-textarea tw:d-textarea-bordered tw:w-full"
            elif isinstance(field.widget, forms.Select):
                css = "tw:d-select tw:d-select-bordered tw:w-full"
            elif isinstance(field.widget, forms.ClearableFileInput):
                css = "tw:file-input tw:file-input-bordered tw:w-full"
            elif isinstance(field.widget, forms.CheckboxInput):
                css = "tw:d-checkbox tw:d-checkbox-primary"
            else:
                css = "tw:d-input tw:d-input-bordered tw:w-full"
            field.widget.attrs.setdefault("class", css)

    def clean_attachments(self):
        files = self.cleaned_data.get("attachments") or []
        allowed = {
            ".csv",
            ".xlsx",
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
