from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import translate_url
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from urllib.parse import urlsplit, urlunsplit


def permission_denied_view(request, exception=None):
    return render(request, "errors/403.html", status=403)


def not_found_view(request, exception=None):
    return render(request, "errors/404.html", status=404)


def server_error_view(request):
    return render(request, "errors/500.html", status=500)


@require_POST
def switch_language(request):
    """Switch locale and explicitly translate an i18n-prefixed return URL."""
    language = request.POST.get("language", "en")
    if language not in dict(settings.LANGUAGES):
        language = settings.LANGUAGE_CODE
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = "/"
    translated = translate_url(next_url, language)
    parts = urlsplit(translated)
    default_language = settings.LANGUAGE_CODE.split("-")[0]
    if language == default_language:
        for code, _label in settings.LANGUAGES:
            if code == default_language:
                continue
            prefix = f"/{code}"
            if parts.path == prefix or parts.path.startswith(prefix + "/"):
                clean_path = parts.path[len(prefix):] or "/"
                parts = parts._replace(path=clean_path)
                translated = urlunsplit(parts)
                break
    elif not (parts.path == f"/{language}" or parts.path.startswith(f"/{language}/")):
        parts = parts._replace(path=f"/{language}{parts.path if parts.path.startswith('/') else '/' + parts.path}")
        translated = urlunsplit(parts)
    response = HttpResponseRedirect(translated)
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        language,
        max_age=settings.LANGUAGE_COOKIE_AGE,
        path=settings.LANGUAGE_COOKIE_PATH,
        domain=settings.LANGUAGE_COOKIE_DOMAIN,
        secure=settings.LANGUAGE_COOKIE_SECURE,
        httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE,
    )
    return response


@require_POST
def switch_theme(request):

    theme = request.POST.get("theme", "light")

    if theme not in ["light", "dark"]:
        theme = "light"

    next_url = request.POST.get("next") or "/"

    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = "/"

    response = HttpResponseRedirect(next_url)

    response.set_cookie(
        "glis_theme",
        theme,
        max_age=365 * 24 * 60 * 60,
        path="/",
        secure=not settings.DEBUG,
        httponly=False,
        samesite="Lax",
    )

    return response




