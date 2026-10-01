"""Choice groups whose containers do not inherit single-control styling."""
from django import forms


class ChoiceGroupMixin:
    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        # Django copies widget classes to both the group and each input.
        # Bootstrap's control class belongs only on the actual inputs.
        container_attrs = dict(context['widget']['attrs'])
        classes = container_attrs.get('class', '').split()
        classes = [name for name in classes if name not in {'form-check-input', 'glis-switch'}]
        container_attrs['class'] = ' '.join(['choice-options', *classes])
        context['widget']['attrs'] = container_attrs
        return context


class CheckboxSelectMultiple(ChoiceGroupMixin, forms.CheckboxSelectMultiple):
    pass


class RadioSelect(ChoiceGroupMixin, forms.RadioSelect):
    pass
