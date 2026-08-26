from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _
from .models import UserProfile


class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label=_("Email or username"), widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "username", "autofocus": True}))
    password = forms.CharField(label=_("Password"), strip=False, widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "current-password"}))

    error_messages = {"invalid_login": _("The email/username or password is incorrect. Check Caps Lock and try again."), "inactive": _("This account is inactive.")}

    def clean(self):
        identifier = self.cleaned_data.get("username", "").strip()
        password = self.cleaned_data.get("password")
        if identifier and password:
            User = get_user_model()
            match = User.objects.filter(email__iexact=identifier).first()
            username = match.get_username() if match else identifier
            self.user_cache = authenticate(self.request, username=username, password=password)
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class UserProfileForm(forms.Form):
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"class": "form-control"}))
    last_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))
    phone = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    organization = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    job_title = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    department = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    bio = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}))
    preferred_language = forms.ChoiceField(choices=UserProfile._meta.get_field("preferred_language").choices, widget=forms.Select(attrs={"class": "form-select"}))
    theme = forms.ChoiceField(choices=UserProfile._meta.get_field("theme").choices, widget=forms.Select(attrs={"class": "form-select"}))
    sidebar_mode = forms.ChoiceField(label=_("Portal navigation"), choices=UserProfile.SidebarMode.choices, widget=forms.Select(attrs={"class": "form-select"}))
    avatar = forms.ImageField(required=False, widget=forms.FileInput(attrs={"class": "form-control", "accept": "image/png,image/jpeg,image/webp"}))
    remove_avatar = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    email_notifications = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    browser_notifications = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    def __init__(self, *args, user, **kwargs):
        self.user = user
        profile = user.profile
        kwargs.setdefault("initial", {
            "first_name": user.first_name, "last_name": user.last_name, "email": user.email,
            "phone": profile.phone, "organization": profile.organization, "job_title": profile.job_title,
            "department": profile.department, "bio": profile.bio, "preferred_language": profile.preferred_language,
            "theme": profile.theme, "sidebar_mode": profile.sidebar_mode, "email_notifications": profile.email_notifications,
            "browser_notifications": profile.browser_notifications,
        })
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError(_("This email address is already in use."))
        return email

    def save(self):
        user, profile = self.user, self.user.profile
        old_email = user.email
        user.first_name, user.last_name, user.email = self.cleaned_data["first_name"], self.cleaned_data["last_name"], self.cleaned_data["email"]
        user.save(update_fields=["first_name", "last_name", "email"])
        if old_email.lower() != user.email.lower():
            from allauth.account.models import EmailAddress
            primary = EmailAddress.objects.filter(user=user, primary=True).first()
            if primary:
                primary.email, primary.verified = user.email, False
                primary.save(update_fields=["email", "verified"])
            else:
                EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=False)
        for field in ("phone", "organization", "job_title", "department", "bio", "preferred_language", "theme", "sidebar_mode", "email_notifications", "browser_notifications"):
            setattr(profile, field, self.cleaned_data[field])
        if self.cleaned_data.get("remove_avatar") and profile.avatar:
            profile.avatar.delete(save=False)
            profile.avatar = ""
        elif self.cleaned_data.get("avatar"):
            profile.avatar = self.cleaned_data["avatar"]
        profile.save()
        return user
