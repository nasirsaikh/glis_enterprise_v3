from django import forms

from .models import Member, MemberTransaction, Policy
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
        self.fields["policy"].queryset = (
            visible_policies(user) if user else Policy.objects.none()
        )
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
        for field in self.fields.values():
            field.widget.attrs.setdefault(
                "class",
                "tw:d-select tw:d-select-bordered tw:w-full"
                if isinstance(field.widget, forms.Select)
                else "tw:d-input tw:d-input-bordered tw:w-full",
            )


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
            raise forms.ValidationError(
                "Provide at least one member identifier."
            )
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
