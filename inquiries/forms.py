import json

from django import forms
from django.utils.translation import gettext_lazy as _
from portfolio.services.shortlist import public_selection
from portfolio.service_content import ServiceKind


class ContactForm(forms.Form):
    name = forms.CharField(label=_("Name"), max_length=120, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    email = forms.EmailField(label=_("Email"), widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    organization = forms.CharField(label=_("Organization"), max_length=160, required=False,
                                    widget=forms.TextInput(attrs={"autocomplete": "organization"}))
    assignment_type = forms.ChoiceField(label=_("Assignment"), required=False, choices=[
        ("", _("Select an option")), ("race", _("Race / endurance event")),
        ("team", _("Team sport")), ("athlete", _("Athlete story")), ("event", _("Other event")),
    ], widget=forms.HiddenInput)
    service = forms.ChoiceField(label=_("Photography service"), required=False,
                               choices=[("", _("Select an option")), *ServiceKind.choices])
    event_date = forms.DateField(label=_("Event date"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    location = forms.CharField(label=_("Location"), max_length=160, required=False)
    message = forms.CharField(label=_("Your project"), max_length=10000,
                              widget=forms.Textarea(attrs={"rows": 5}))
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))
    submission_token = forms.CharField(widget=forms.HiddenInput)
    selected_photos = forms.CharField(required=False, max_length=1000, widget=forms.HiddenInput, initial="[]")

    def clean_selected_photos(self):
        try:
            return public_selection(json.loads(self.cleaned_data["selected_photos"] or "[]"))
        except (ValueError, TypeError):
            raise forms.ValidationError(_("Please review your saved photographs."))

    def clean_name(self):
        name = self.cleaned_data["name"]
        if "\r" in name or "\n" in name:
            raise forms.ValidationError(_("Enter your name on one line."))
        return name
