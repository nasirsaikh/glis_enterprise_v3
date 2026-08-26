from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core.exceptions import PermissionDenied
from .models import AccountPolicy, UserProfile


class GLISSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        email = (sociallogin.user.email or "").lower()
        policy = AccountPolicy.load()
        domains = {d.lower().lstrip("@") for d in policy.allowed_email_domains}
        if domains and email.split("@")[-1] not in domains:
            raise PermissionDenied("This email domain is not approved for GLIS access.")

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        policy = AccountPolicy.load()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = policy.default_external_role
        profile.is_external = True
        profile.is_approved = not policy.external_users_require_approval
        profile.save()
        if policy.default_external_group:
            user.groups.add(policy.default_external_group)
        return user
