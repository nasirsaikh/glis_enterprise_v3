"""Email-link and one-time email-code recovery with shared rate limits."""
from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordResetForm
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from services.ticket_notifications import account_enabled
from .models import PasswordResetChallenge


def digest(purpose, value):
    return salted_hmac(f'glis.password-reset.{purpose}', str(value), algorithm='sha256').hexdigest()


def otp_code(challenge):
    # The random challenge nonce and server secret produce an unpredictable
    # code. Queue payloads and database rows never contain the plaintext OTP.
    return str(int(digest('code', challenge.pk), 16) % 1000000).zfill(6)


def password_stamp(user):
    return digest('password-state', f'{user.pk}:{user.password}:{user.email}')


@transaction.atomic
def issue_challenge(request, email, method):
    now = timezone.now()
    email_key = digest('email', email.casefold())
    ip_key = digest('ip', request.META.get('REMOTE_ADDR', ''))
    matches = list(get_user_model().objects.select_for_update().filter(email__iexact=email, is_active=True).order_by('pk')[:2])
    recent = PasswordResetChallenge.objects.filter(created_at__gt=now-timedelta(hours=1))
    if recent.filter(email_digest=email_key).count() >= 5 or recent.filter(ip_digest=ip_key).count() >= 20:
        return None
    if recent.filter(email_digest=email_key, created_at__gt=now-timedelta(seconds=60)).exists():
        return None
    user = matches[0] if len(matches) == 1 and account_enabled(matches[0]) and matches[0].has_usable_password() else None
    request.session.cycle_key()
    challenge = PasswordResetChallenge.objects.create(user=user, method=method, email_digest=email_key, ip_digest=ip_key,
        session_digest=digest('session', request.session.session_key), password_stamp=password_stamp(user) if user else '',
        expires_at=now+timedelta(minutes=10))
    request.session['password_reset_challenge'] = str(challenge.pk)
    from apps.job_center.queue import enqueue
    transaction.on_commit(lambda: enqueue('email.password_reset', {'challenge_id':str(challenge.pk)}, priority=1))
    return challenge


def challenge_valid(challenge, request):
    return (challenge and not challenge.consumed_at and challenge.expires_at > timezone.now() and challenge.attempts < 5
            and constant_time_compare(challenge.session_digest, digest('session', request.session.session_key))
            and challenge.user and account_enabled(challenge.user)
            and constant_time_compare(challenge.password_stamp, password_stamp(challenge.user)))


class EligibleResetLinkForm(PasswordResetForm):
    def get_users(self, email):
        return [user for user in super().get_users(email) if account_enabled(user)
                and (not getattr(self, 'recipient', None) or user.pk == self.recipient.pk)]


def deliver_reset(challenge_id):
    challenge = PasswordResetChallenge.objects.select_related('user__profile').filter(pk=challenge_id).first()
    if not challenge or not challenge.user or challenge.consumed_at or challenge.expires_at <= timezone.now():
        return {'success':True, 'sent':0}
    user = challenge.user
    if not account_enabled(user) or not constant_time_compare(challenge.password_stamp, password_stamp(user)):
        return {'success':True, 'sent':0}
    if challenge.method == 'otp':
        context = {'code':otp_code(challenge), 'minutes':10}
        text = render_to_string('emails/password_reset_otp.txt', context)
        html = render_to_string('emails/password_reset_otp.html', context)
        sent = send_mail('GLIS password reset code', text, settings.DEFAULT_FROM_EMAIL, [user.email], html_message=html)
    else:
        origin = urlsplit(settings.SITE_URL)
        form = EligibleResetLinkForm({'email':user.email}); form.recipient=user
        if not form.is_valid(): return {'success':True, 'sent':0}
        form.save(domain_override=origin.netloc, use_https=origin.scheme=='https', from_email=settings.DEFAULT_FROM_EMAIL,
                  subject_template_name='emails/password_reset_link_subject.txt', email_template_name='emails/password_reset_link.txt',
                  html_email_template_name='emails/password_reset_link.html')
        sent = 1
    return {'success':True, 'sent':sent}
