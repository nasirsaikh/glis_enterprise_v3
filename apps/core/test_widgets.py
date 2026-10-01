from html.parser import HTMLParser

from django import forms
from django.test import SimpleTestCase

from .widgets import CheckboxSelectMultiple, RadioSelect


class WidgetMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class ChoiceGroupTests(SimpleTestCase):
    def test_checkboxes_keep_labels_values_and_selected_state_on_repeated_render(self):
        class ChoiceForm(forms.Form):
            users = forms.MultipleChoiceField(choices=[('1', 'First user'), ('2', 'Second user')],
                widget=CheckboxSelectMultiple(attrs={'class':'checkbox checkbox-primary'}))

        form = ChoiceForm({'users':['1','2']})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['users'], ['1','2'])
        for _ in range(2):
            markup = WidgetMarkup(str(form['users']))
            container = markup.tags[0][1]
            self.assertEqual(container['id'], 'id_users')
            self.assertNotIn('checkbox', container['class'].split())
            inputs = [attrs for tag, attrs in markup.tags if tag == 'input']
            self.assertEqual([item['value'] for item in inputs], ['1','2'])
            self.assertTrue(all('checked' in item and item['name']=='users' for item in inputs))
            self.assertTrue(all('checkbox' in item['class'].split() for item in inputs))
            self.assertEqual([attrs['for'] for tag,attrs in markup.tags if tag=='label'],
                [item['id'] for item in inputs])

    def test_radio_group_keeps_one_selected_value_and_disabled_controls(self):
        widget = RadioSelect(attrs={'class':'radio radio-primary','disabled':True},
            choices=[('approve','Approve'), ('reject','Reject')])
        markup = WidgetMarkup(widget.render('decision','reject',attrs={'id':'id_decision'}))
        self.assertNotIn('radio', markup.tags[0][1]['class'].split())
        inputs = [attrs for tag,attrs in markup.tags if tag=='input']
        self.assertEqual([item['value'] for item in inputs if 'checked' in item], ['reject'])
        self.assertTrue(all('disabled' in item and 'radio' in item['class'].split() for item in inputs))
