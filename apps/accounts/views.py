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


def _style_password_form(form):
    for field in form.fields.values():
        field.widget.attrs["class"] = "form-control"
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
