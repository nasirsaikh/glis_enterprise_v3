from django import forms
from django.utils.translation import gettext_lazy as _


class OneTimeCodeWidget(forms.MultiWidget):
    template_name = 'account/widgets/otp_code.html'

    def __init__(self, attrs=None):
        widgets = [forms.TextInput(attrs={
            'class': 'form-control otp-digit text-center',
            'inputmode': 'numeric', 'pattern': '[0-9]', 'maxlength': 1,
            'autocomplete': 'one-time-code' if index == 0 else 'off',
            'aria-label': _('Code digit %(number)s') % {'number': index + 1},
        }) for index in range(6)]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        return list(str(value).ljust(6)[:6]) if value else [''] * 6
