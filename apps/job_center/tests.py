from unittest.mock import patch
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .models import JobExecution, ScheduledJob


class JobAdminRenderingTests(TestCase):
    def test_status_badges_and_registered_handlers_render_with_django_61(self):
        job = ScheduledJob.objects.create(name='Compatibility job', handler='examples.health_check')
        job_admin = admin.site._registry[ScheduledJob]
        for status in JobExecution.Status.values:
            job.last_status = status
            str(job_admin.status_badge(job))
            execution = JobExecution.objects.create(job=job, status=status)
            str(admin.site._registry[JobExecution].status_badge(execution))
        with patch('apps.job_center.admin.get_registered_jobs', return_value={'<unsafe>': object(), 'safe': object()}):
            self.assertIn('&lt;unsafe&gt;', job_admin.registered_handlers(job))
        self.client.force_login(get_user_model().objects.create_superuser('job-admin', 'job@example.test', 'test'))
        self.assertEqual(self.client.get(reverse('admin:job_center_jobexecution_changelist')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:job_center_scheduledjob_changelist')).status_code, 200)
