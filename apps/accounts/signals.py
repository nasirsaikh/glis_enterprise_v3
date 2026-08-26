from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.core.models import AuditLog
from .models import UserProfile


@receiver(post_save, sender=get_user_model())
def ensure_profile(sender, instance, created, **kwargs):
    UserProfile.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def audit_login(request, user, **kwargs):
    AuditLog.record(request=request, actor=user, action="account.login", summary="Successful user login", sensitivity="security")
