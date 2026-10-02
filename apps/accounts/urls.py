from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy

urlpatterns = [
    path('password/reset/',views.password_reset_request,name='password_reset_request'),
    path('password/reset/otp/',views.password_reset_otp,name='password_reset_otp'),
    path('password/reset/confirm/<uidb64>/<token>/',views.EligiblePasswordResetConfirmView.as_view(template_name='account/reset_confirm.html',success_url=reverse_lazy('accounts:password_reset_complete')),name='password_reset_confirm'),
    path('password/reset/complete/',auth_views.PasswordResetCompleteView.as_view(template_name='account/reset_complete.html'),name='password_reset_complete'),
    path("profile/", views.profile, name="profile"),
    path("profile/password/", views.change_password, name="change_password"),
    path("profile/sidebar/", views.sidebar_preference, name="sidebar_preference"),
    path("profile/theme/", views.theme_preference, name="theme_preference"),
]
