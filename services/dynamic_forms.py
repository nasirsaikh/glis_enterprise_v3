import re
from datetime import date
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import get_language
from .datasources import DataSourceRegistry


CONTROL_WIDGETS = {
    "text": forms.TextInput, "tel": forms.TextInput, "email": forms.EmailInput,
    "textarea": forms.Textarea, "richtext": forms.Textarea, "number": forms.NumberInput,
    "currency": forms.NumberInput, "date": forms.DateInput, "datetime": forms.DateTimeInput,
    "url": forms.URLInput, "rating": forms.NumberInput, "tags": forms.TextInput,
}


def localized(field: dict, key: str):
    language = (get_language() or "en").split("-")[0]
    return field.get(f"{key}_{language}") or field.get(key) or field.get(f"{key}_en") or field.get("name", "")


class DynamicTicketForm(forms.Form):
    def __init__(self, *args, schema=None, user=None, **kwargs):
        self.schema = schema or {}
        self.user = user
        super().__init__(*args, **kwargs)
        role = getattr(getattr(user, "profile", None), "role", "guest")
        for spec in self.schema.get("fields", []):
            allowed_roles = spec.get("visible_to_roles") or []
            if allowed_roles and role not in allowed_roles and not getattr(user, "is_superuser", False):
                continue
            condition = spec.get("visible_when") or {}
            if condition and self.is_bound:
                actual = self.data.get(condition.get("field"))
                expected = condition.get("value")
                operator = condition.get("operator", "equals")
                visible = (str(actual) == str(expected)) if operator == "equals" else (str(actual) != str(expected))
                if not visible:
                    continue
            if not spec.get("show_in_form", True):
                continue
            field = self._build_field(spec)
            editable_roles = spec.get("editable_to_roles") or []
            if editable_roles and role not in editable_roles and not getattr(user, "is_superuser", False):
                field.disabled = True
            self.fields[spec["name"]] = field

    def _build_field(self, spec):
        control = spec.get("control", "text")
        validation = spec.get("validation", {})
        common = {
            "label": localized(spec, "label"), "required": bool(spec.get("required")),
            "help_text": localized(spec, "help_text"),
        }
        if control in {"select", "radio", "multiselect"}:
            source = spec.get("data_source", {})
            choices = source.get("options", [])
            choices = [(str(x.get("value")), x.get("label")) for x in choices]
            if source.get("registry"):
                choices = DataSourceRegistry.choices(source["registry"], user=self.user)
            if control == "multiselect":
                return forms.MultipleChoiceField(choices=choices, widget=forms.SelectMultiple(attrs={"class": "form-select"}), **common)
            widget = forms.RadioSelect if control == "radio" else forms.Select(attrs={"class": "form-select"})
            return forms.ChoiceField(choices=choices, widget=widget, **common)
        if control in {"checkbox", "switch"}:
            return forms.BooleanField(widget=forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch" if control == "switch" else "checkbox"}), **common)
        if control == "file":
            return forms.FileField(**common)
        if control in {"number", "currency", "rating"}:
            return forms.DecimalField(min_value=validation.get("min"), max_value=validation.get("max"), decimal_places=2, widget=CONTROL_WIDGETS[control](attrs={"class": "form-control"}), **common)
        if control == "date":
            field = forms.DateField(widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}), **common)
        elif control == "datetime":
            field = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}), **common)
        elif control == "email":
            field = forms.EmailField(max_length=validation.get("max_length"), widget=forms.EmailInput(attrs={"class": "form-control"}), **common)
        elif control == "url":
            field = forms.URLField(widget=forms.URLInput(attrs={"class": "form-control"}), **common)
        else:
            widget_cls = CONTROL_WIDGETS.get(control, forms.TextInput)
            attrs = {"class": "form-control", "placeholder": localized(spec, "placeholder")}
            if control in {"textarea", "richtext"}:
                attrs["rows"] = 5
            if control == "richtext":
                attrs["class"] += " richtext-source"
            if not spec.get("editable", True):
                attrs["readonly"] = True
            field = forms.CharField(min_length=validation.get("min_length"), max_length=validation.get("max_length"), widget=widget_cls(attrs=attrs), **common)
        default = spec.get("default", {})
        if default.get("source") == "system" and default.get("value") == "today":
            field.initial = date.today
        elif default.get("source") == "literal":
            field.initial = default.get("value")
        return field

    def clean(self):
        cleaned = super().clean()
        for spec in self.schema.get("fields", []):
            name = spec.get("name")
            if name not in self.fields:
                continue
            value = cleaned.get(name)
            pattern = spec.get("validation", {}).get("regex")
            if value and pattern and not re.fullmatch(pattern, str(value)):
                self.add_error(name, spec.get("validation", {}).get("regex_message", "Invalid format."))
            if spec.get("validation", {}).get("max") == "today" and value and value > date.today():
                self.add_error(name, "The date cannot be in the future.")
            required_when = spec.get("required_when") or {}
            if required_when and str(cleaned.get(required_when.get("field"))) == str(required_when.get("value")) and not value:
                self.add_error(name, "This field is required for the selected option.")
            lookup = spec.get("lookup") or {}
            if lookup.get("registry") and value:
                result = DataSourceRegistry.choices(lookup["registry"], user=self.user, params={name: value, "claim_number": value})
                if lookup.get("required_match") and not result:
                    self.add_error(name, lookup.get("not_found_message", "The supplied reference was not found."))
                elif isinstance(result, dict):
                    for source_key, target_key in lookup.get("result_map", {}).items():
                        cleaned[target_key] = result.get(source_key)
        return cleaned


def safe_schema_payload(schema):
    """Remove raw SQL metadata before sending a schema to browsers or external AI."""
    result = dict(schema or {})
    result["fields"] = []
    for original in (schema or {}).get("fields", []):
        field = dict(original)
        source = dict(field.get("data_source", {}))
        source.pop("query", None)
        lookup = dict(field.get("lookup", {}))
        lookup.pop("query", None)
        field["data_source"], field["lookup"] = source, lookup
        result["fields"].append(field)
    return result


def build_api_payload(schema: dict, values: dict) -> dict:
    """Map validated values to a configured API shape without evaluating code."""
    payload = dict(schema.get("api_defaults") or {})
    sections: dict[str, dict] = {}
    converters = {
        "int": lambda value: int(value) if value not in (None, "") else None,
        "float": lambda value: float(value) if value not in (None, "") else None,
        "string": lambda value: str(value) if value is not None else "",
        "datetime": lambda value: value.isoformat() if hasattr(value, "isoformat") else str(value),
        "bool": lambda value: bool(value),
    }
    for spec in schema.get("fields", []):
        if spec.get("send_to_api", True) is False or spec.get("name") not in values:
            continue
        value = values.get(spec["name"])
        converter = converters.get(spec.get("api_type", "string"), converters["string"])
        try:
            value = converter(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"Cannot map {spec['name']} to {spec.get('api_type')}.") from exc
        target_name = spec.get("api_name") or spec["name"]
        section = spec.get("api_section", "root")
        if section == "root":
            payload[target_name] = value
        else:
            sections.setdefault(section, {})[target_name] = value
    payload.update(sections)
    return payload
