from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.accounts.forms import EmailOrUsernameAuthenticationForm
from apps.core.admin_order import install_numbered_admin_index
from apps.core.views import switch_language

install_numbered_admin_index(admin.site)

urlpatterns = [
    path("i18n/switch/", switch_language, name="switch_language"),
    path("i18n/", include("django.conf.urls.i18n")),
]

# Keep all GLIS application URLs ahead of django CMS. django CMS must remain
# last because its URLconf is a catch-all for CMS-managed pages.
urlpatterns += i18n_patterns(
    path("admin/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="account/login.html",
            authentication_form=EmailOrUsernameAuthenticationForm,
            redirect_authenticated_user=True,
        ),
        name="account_login",
    ),
    path("accounts/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),
    path("accounts/", include("allauth.urls")),
    path("portal/", include(("apps.tickets.urls", "portal"), namespace="portal")),
    path("knowledge/", include(("apps.knowledge.urls", "knowledge"), namespace="knowledge")),
    path("analytics/", include(("apps.orchestrator.urls", "orchestrator"), namespace="orchestrator")),
    path("api/v1/", include("apps.api.urls")),

    # Legacy GLIS settings endpoints retained during content migration.
    # Home is kept at / until the first django CMS homepage is published.
    path("", include(("apps.app_settings.urls", "public"), namespace="public")),

    # django CMS-managed pages live below /pages/ during the migration. This
    # avoids changing existing public URLs before content has been migrated.
    path("pages/", include("cms.urls")),
    prefix_default_language=False,
)

handler403 = "apps.core.views.permission_denied_view"
handler404 = "apps.core.views.not_found_view"
handler500 = "apps.core.views.server_error_view"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
