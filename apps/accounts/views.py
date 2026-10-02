from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from .forms import UserProfileForm
from .models import UserProfile
from django import forms
from django.contrib.auth.forms import SetPasswordForm
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .models import PasswordResetChallenge
from django.contrib.auth.views import PasswordResetConfirmView


class EligiblePasswordResetConfirmView(PasswordResetConfirmView):
    def get_user(self, uidb64):
        from services.ticket_notifications import account_enabled
        user = super().get_user(uidb64)
        return user if account_enabled(user) else None

    def get_form(self, form_class=None):
        return _style_password_form(super().get_form(form_class))


class ResetRequestForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={'class':'form-control','autocomplete':'email'}))
    method = forms.ChoiceField(choices=[('link','Email reset link'),('otp','Email one-time code (OTP)')], initial='link', widget=forms.RadioSelect)


class ResetCodeForm(forms.Form):
    code = forms.RegexField(r'^\d{6}$', label='One-time code', widget=forms.TextInput(attrs={'class':'form-control','inputmode':'numeric','autocomplete':'one-time-code','maxlength':6}))


@never_cache
@require_http_methods(['GET','POST'])
def password_reset_request(request):
    form = ResetRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        from .password_reset import issue_challenge
        issue_challenge(request, form.cleaned_data['email'], form.cleaned_data['method'])
        if form.cleaned_data['method'] == 'otp':return redirect('accounts:password_reset_otp')
        return render(request,'account/reset_sent.html')
    return render(request,'account/reset_request.html',{'form':form})


@never_cache
@sensitive_post_parameters('code','new_password1','new_password2')
@require_http_methods(['GET','POST'])
def password_reset_otp(request):
    from .password_reset import challenge_valid, otp_code
    from uuid import UUID
    try: challenge_id=UUID(request.session.get('password_reset_challenge',''))
    except (ValueError, TypeError):challenge_id=None
    code_form=ResetCodeForm(request.POST or None)
    with transaction.atomic():
        challenge=PasswordResetChallenge.objects.select_for_update().filter(pk=challenge_id,method='otp').first()
        user=None
        if challenge and challenge.user_id:
            from django.contrib.auth import get_user_model
            user=get_user_model().objects.select_for_update().get(pk=challenge.user_id)
            challenge.user=user
        # Until the code is verified, even password validation must avoid
        # revealing whether an account (or a matching username) exists.
        password_form=_style_password_form(SetPasswordForm(None,request.POST or None))
        if request.method=='POST' and code_form.is_valid():
            valid=challenge_valid(challenge,request) and constant_time_compare(code_form.cleaned_data['code'],otp_code(challenge))
            if not valid:
                if challenge and not challenge.consumed_at:
                    challenge.attempts=min(5,challenge.attempts+1)
                    challenge.save(update_fields=['attempts','updated_at'])
                code_form.add_error('code','The code is invalid or expired. Request a new code to continue.')
            else:
                password_form=_style_password_form(SetPasswordForm(user,request.POST))
                if password_form.is_valid():
                    password_form.save()
                    challenge.consumed_at=timezone.now()
                    challenge.save(update_fields=['consumed_at','updated_at'])
                    request.session.pop('password_reset_challenge',None)
                    request.session.cycle_key()
                    return redirect('accounts:password_reset_complete')
    return render(request,'account/reset_otp.html',{'code_form':code_form,'password_form':password_form})


def _style_password_form(form):
    for field in form.fields.values():
        field.widget.attrs["class"] = "form-control w-100"
    return form


@login_required
def profile(request):
    form = UserProfileForm(request.POST or None, request.FILES or None, user=request.user)
    password_form = _style_password_form(PasswordChangeForm(request.user, prefix="password"))
    if request.method == "POST" and request.POST.get("action") == "profile" and form.is_valid():
        form.save()
        messages.success(request, "Your profile was updated.")
        response = redirect("accounts:profile")
        response.set_cookie(settings.LANGUAGE_COOKIE_NAME, request.user.profile.preferred_language, max_age=settings.LANGUAGE_COOKIE_AGE, samesite=settings.LANGUAGE_COOKIE_SAMESITE)
        return response
    return render(request, "account/profile.html", {"form": form, "password_form": password_form})


@login_required
@require_POST
def change_password(request):
    form = _style_password_form(PasswordChangeForm(request.user, request.POST, prefix="password"))
    if form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Your password was changed securely.")
        return redirect("accounts:profile")
    profile_form = UserProfileForm(user=request.user)
    return render(request, "account/profile.html", {"form": profile_form, "password_form": form}, status=422)


@login_required
@require_POST
def sidebar_preference(request):
    mode = request.POST.get("mode", "").strip()
    valid_modes = {value for value, _label in UserProfile.SidebarMode.choices}
    if mode not in valid_modes:
        return JsonResponse({"error": "Invalid sidebar mode."}, status=400)
    profile = request.user.profile
    profile.sidebar_mode = mode
    profile.save(update_fields=["sidebar_mode", "updated_at"])
    return JsonResponse({"mode": mode})


@login_required
@require_POST
def theme_preference(request):
    theme = request.POST.get("theme", "").strip()
    valid_themes = {value for value, _label in UserProfile.THEME_CHOICES}
    if theme not in valid_themes:
        return JsonResponse({"error": "Invalid theme."}, status=400)
    profile = request.user.profile
    profile.theme = theme
    profile.save(update_fields=["theme", "updated_at"])
    return JsonResponse({"theme": theme})
