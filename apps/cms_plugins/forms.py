from django import forms
from django_summernote.widgets import SummernoteWidget

from .models import CustomWebSection


class CustomWebSectionForm(forms.ModelForm):
    class Meta:
        model = CustomWebSection

        fields = [
            "title",
            "html_content",
            "css_content",
            "javascript_content",
            "is_active",
        ]

        widgets = {
            "html_content": SummernoteWidget(
                attrs={
                    "summernote": {
                        "width": "100%",
                        "height": "450px",
                    }
                }
            ),

            "css_content": forms.Textarea(
                attrs={
                    "rows": 15,
                    "class": "vLargeTextField",
                    "style": (
                        "font-family:Consolas,Monaco,monospace;"
                        "font-size:13px;"
                    ),
                }
            ),

            "javascript_content": forms.Textarea(
                attrs={
                    "rows": 15,
                    "class": "vLargeTextField",
                    "style": (
                        "font-family:Consolas,Monaco,monospace;"
                        "font-size:13px;"
                    ),
                }
            ),
        }