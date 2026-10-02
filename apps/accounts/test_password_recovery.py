"""Exercise both public recovery paths without delivering real email."""
import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import EmailOrUsernameAuthenticationForm
from .models import PasswordResetChallenge
from .password_reset import deliver_reset, otp_code


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', SITE_URL='https://portal.example.test')
class PasswordRecoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('recovery-user', 'recovery@example.test', 'OriginalPass!8739')

    def request_reset(self, method='otp', email=None, client=None):
        client = client or self.client
        with patch('apps.job_center.queue.enqueue') as enqueue, self.captureOnCommitCallbacks(execute=True):
            response = client.post(reverse('accounts:password_reset_request'), {'email': email or self.user.email, 'method': method})
        return response, enqueue

    def challenge(self, client=None):
        return PasswordResetChallenge.objects.get(pk=(client or self.client).session['password_reset_challenge'])

    def confirm_otp(self, challenge, code=None, client=None):
        return (client or self.client).post(reverse('accounts:password_reset_otp'), {
            'code': code or otp_code(challenge), 'new_password1': 'ReplacementPass!5247', 'new_password2': 'ReplacementPass!5247',
        })

    def test_login_and_legacy_reset_url_offer_both_choices(self):
        response = self.client.get(reverse('account_reset_password'))
        self.assertContains(response, 'Email reset link')
        self.assertContains(response, 'Email one-time code (OTP)')
        self.assertContains(self.client.get(reverse('account_login')), reverse('accounts:password_reset_request'))

    def test_otp_job_contains_only_nonce_and_email_is_personal(self):
        response, enqueue = self.request_reset()
        self.assertRedirects(response, reverse('accounts:password_reset_otp'))
        challenge = self.challenge()
        enqueue.assert_called_once_with('email.password_reset', {'challenge_id': str(challenge.pk)}, priority=1)
        self.assertNotIn(otp_code(challenge), str(enqueue.call_args))
        self.assertEqual(deliver_reset(challenge.pk)['sent'], 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn(otp_code(challenge), mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].alternatives[0].mimetype, 'text/html')

    def test_otp_resets_password_once_and_does_not_sign_in(self):
        self.request_reset(); challenge = self.challenge()
        self.assertRedirects(self.confirm_otp(challenge), reverse('accounts:password_reset_complete'))
        self.user.refresh_from_db(); challenge.refresh_from_db()
        self.assertTrue(self.user.check_password('ReplacementPass!5247'))
        self.assertIsNotNone(challenge.consumed_at)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(self.confirm_otp(challenge), 'invalid or expired')
        self.assertEqual(deliver_reset(challenge.pk)['sent'], 0)

    def test_invalid_password_preserves_valid_code_for_retry(self):
        self.request_reset(); challenge = self.challenge()
        response = self.client.post(reverse('accounts:password_reset_otp'), {
            'code': otp_code(challenge), 'new_password1': 'ReplacementPass!5247', 'new_password2': 'Mismatch!5738',
        })
        self.assertContains(response, 'password fields')
        challenge.refresh_from_db(); self.assertIsNone(challenge.consumed_at)
        self.assertRedirects(self.confirm_otp(challenge), reverse('accounts:password_reset_complete'))

    def test_invalid_code_does_not_expose_account_specific_password_errors(self):
        self.request_reset(); challenge = self.challenge()
        wrong = '000001' if otp_code(challenge) == '000000' else '000000'
        response = self.client.post(reverse('accounts:password_reset_otp'), {
            'code': wrong, 'new_password1': self.user.username, 'new_password2': self.user.username,
        })
        self.assertContains(response, 'invalid or expired')
        self.assertNotContains(response, 'too similar to the username')
        self.assertIsNone(response.context['password_form'].user)
        response = self.client.post(reverse('accounts:password_reset_otp'), {
            'code': otp_code(challenge), 'new_password1': self.user.username, 'new_password2': self.user.username,
        })
        self.assertContains(response, 'too similar to the username')
        challenge.refresh_from_db(); self.assertIsNone(challenge.consumed_at)

    def test_code_expires_and_five_failed_guesses_block_correct_code(self):
        self.request_reset(); challenge = self.challenge()
        wrong = '000001' if otp_code(challenge) == '000000' else '000000'
        for _ in range(5):
            self.assertContains(self.confirm_otp(challenge, wrong), 'invalid or expired')
        challenge.refresh_from_db(); self.assertEqual(challenge.attempts, 5)
        self.assertContains(self.confirm_otp(challenge), 'invalid or expired')
        PasswordResetChallenge.objects.filter(pk=challenge.pk).update(attempts=0, expires_at=timezone.now()-timedelta(seconds=1))
        self.assertContains(self.confirm_otp(challenge), 'invalid or expired')
        self.assertEqual(deliver_reset(challenge.pk)['sent'], 0)

    def test_code_is_bound_to_requesting_session(self):
        self.request_reset(); challenge = self.challenge()
        other = Client(); session = other.session
        session['password_reset_challenge'] = str(challenge.pk); session.save()
        self.assertContains(self.confirm_otp(challenge, client=other), 'invalid or expired')
        self.user.refresh_from_db(); self.assertTrue(self.user.check_password('OriginalPass!8739'))

    def test_password_change_invalidates_pending_code(self):
        self.request_reset(); challenge = self.challenge()
        self.user.set_password('ChangedElsewhere!9386'); self.user.save()
        self.assertEqual(deliver_reset(challenge.pk)['sent'], 0)
        self.assertContains(self.confirm_otp(challenge), 'invalid or expired')

    def test_ineligible_accounts_do_not_receive_recovery_email(self):
        for state in ('inactive', 'locked', 'unapproved', 'expired'):
            with self.subTest(state=state):
                user = get_user_model().objects.create_user('recover-'+state, state+'@example.test', 'OriginalPass!8739')
                if state == 'inactive': user.is_active = False; user.save()
                if state == 'locked': user.profile.is_locked = True
                if state == 'unapproved': user.profile.is_approved = False
                if state == 'expired': user.profile.guest_access_expires_at = timezone.now()-timedelta(days=1)
                user.profile.save()
                self.request_reset(email=user.email)
                self.assertEqual(deliver_reset(self.challenge().pk)['sent'], 0)

    def test_unknown_address_and_cooldown_have_generic_responses(self):
        response, _ = self.request_reset('link', 'missing@example.test')
        self.assertContains(response, 'eligible account')
        self.assertIsNone(self.challenge().user_id)
        self.request_reset(); count = PasswordResetChallenge.objects.count()
        response, enqueue = self.request_reset()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PasswordResetChallenge.objects.count(), count)
        enqueue.assert_not_called()

    def test_email_link_uses_trusted_origin_and_can_reset_password_once(self):
        self.request_reset('link')
        self.assertEqual(deliver_reset(self.challenge().pk)['sent'], 1)
        url = re.search(r'https://portal\.example\.test([^\s]+)', mail.outbox[0].body).group(1)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        form_url = response['Location']
        self.assertContains(self.client.get(form_url), 'new_password1')
        response = self.client.post(form_url, {'new_password1': 'ReplacementPass!5247', 'new_password2': 'ReplacementPass!5247'})
        self.assertRedirects(response, reverse('accounts:password_reset_complete'))
        self.user.refresh_from_db(); self.assertTrue(self.user.check_password('ReplacementPass!5247'))
        self.assertNotContains(self.client.get(url, follow=True), 'name="new_password1"')

    def test_lock_after_issue_blocks_link_and_existing_session(self):
        self.request_reset('link'); deliver_reset(self.challenge().pk)
        url = re.search(r'https://portal\.example\.test([^\s]+)', mail.outbox[0].body).group(1)
        self.client.force_login(self.user)
        self.user.profile.is_locked = True; self.user.profile.save()
        self.assertEqual(self.client.get(reverse('accounts:profile')).status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertNotContains(self.client.get(url, follow=True), 'name="new_password1"')
        form = EmailOrUsernameAuthenticationForm(data={'username': self.user.username, 'password': 'OriginalPass!8739'})
        self.assertFalse(form.is_valid())

    def test_security_recovery_ignores_activity_email_opt_out(self):
        self.user.profile.email_notifications = False; self.user.profile.save()
        self.request_reset()
        self.assertEqual(deliver_reset(self.challenge().pk)['sent'], 1)

    def test_hourly_limit_applies_across_both_reset_methods(self):
        for index in range(5):
            self.request_reset('link' if index % 2 else 'otp')
            PasswordResetChallenge.objects.all().update(created_at=timezone.now()-timedelta(seconds=61))
        count = PasswordResetChallenge.objects.count()
        _, enqueue = self.request_reset('link')
        self.assertEqual(count, 5)
        self.assertEqual(PasswordResetChallenge.objects.count(), count)
        enqueue.assert_not_called()
