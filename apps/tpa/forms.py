from django import forms
from .models import MemberTransaction, Policy
from .services.access import visible_policies

class TransactionForm(forms.ModelForm):
    class Meta:
        model=MemberTransaction
        fields=["policy","transaction_type","effective_date","remarks"]
        widgets={"effective_date":forms.DateInput(attrs={"type":"date","class":"tw:d-input tw:d-input-bordered tw:w-full"})}
    def __init__(self,*args,user=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields["policy"].queryset=visible_policies(user) if user else Policy.objects.none()
        for name,field in self.fields.items():
            field.widget.attrs.setdefault("class","tw:d-select tw:d-select-bordered tw:w-full" if isinstance(field.widget,forms.Select) else "tw:d-input tw:d-input-bordered tw:w-full")
