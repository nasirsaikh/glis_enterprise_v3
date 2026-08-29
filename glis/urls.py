from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from apps.accounts.forms import EmailOrUsernameAuthenticationForm
from apps.core.admin_order import install_numbered_admin_index
from apps.core.views import switch_language,switch_theme

install_numbered_admin_index(admin.site)

urlpatterns = [
    path("i18n/switch/", switch_language, name="switch_language"),
    path("theme/switch/",switch_theme,name="switch_theme",),
    path("i18n/", include("django.conf.urls.i18n")),
]

urlpatterns += i18n_patterns(
    path("admin/", admin.site.urls),
    path('visitor-tracker/', include('django_visitor_tracker.urls')),
    path("accounts/login/",auth_views.LoginView.as_view(template_name="account/login.html",authentication_form=EmailOrUsernameAuthenticationForm,redirect_authenticated_user=True,),name="account_login",),
    path("accounts/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("accounts/", include("allauth.urls")),
    path("portal/", include(("apps.tickets.urls", "portal"), namespace="portal")),
    path("documents/", include(("apps.core.document_urls", "documents"), namespace="documents")),
    path("knowledge/", include(("apps.knowledge.urls", "knowledge"), namespace="knowledge")),
    path("analytics/", include(("apps.orchestrator.urls", "orchestrator"), namespace="orchestrator")),
    path("api/v1/", include("apps.api.urls")),
    path("job-center/", include("apps.job_center.urls")),
    path("summernote/",include("django_summernote.urls"),),
    path("", include("cms.urls")),
    prefix_default_language=False,
)

handler403 = "apps.core.views.permission_denied_view"
handler404 = "apps.core.views.not_found_view"
handler500 = "apps.core.views.server_error_view"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
