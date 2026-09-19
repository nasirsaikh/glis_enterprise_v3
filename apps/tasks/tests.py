from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.tickets.models import Category, Product, Project

from .models import RecurringTask, Task
from .services import _add_months, generate_due_tasks


class RecurringTaskGenerationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="owner", email="owner@example.com", password="test-pass")
        self.watcher = User.objects.create_user(username="watcher", email="watcher@example.com", password="test-pass")
        self.project = Project.objects.create(code="TSK", name_en="Tasks")
        self.product = Product.objects.create(project=self.project, code="OPS", name_en="Operations")
        self.category = Category.objects.create(product=self.product, code="MONTHLY", name_en="Monthly task")

    def test_month_end_is_clamped(self):
        self.assertEqual(_add_months(date(2026, 1, 31), 1), date(2026, 2, 28))

    def test_lead_days_create_once_and_copy_watchers(self):
        recurring = RecurringTask.objects.create(
            title="Monthly close",
            project=self.project,
            product=self.product,
            category=self.category,
            owner=self.owner,
            first_due_date=date(2026, 10, 1),
            recurrence=RecurringTask.Frequency.MONTHLY,
            create_days_before=15,
            created_by=self.owner,
            updated_by=self.owner,
        )
        recurring.tagged_users.add(self.watcher)

        before = generate_due_tasks(as_of=date(2026, 9, 15))
        self.assertEqual(before["created"], 0)
        self.assertEqual(Task.objects.count(), 0)

        on_lead_date = generate_due_tasks(as_of=date(2026, 9, 16))
        self.assertEqual(on_lead_date["created"], 1)

        task = Task.objects.get()
        self.assertEqual(task.due_date, date(2026, 10, 1))
        self.assertEqual(task.owner, self.owner)
        self.assertTrue(task.tagged_users.filter(pk=self.watcher.pk).exists())
        self.assertIsNotNone(task.ticket_id)
        self.assertEqual(task.ticket.assignee, self.owner)

        repeated = generate_due_tasks(as_of=date(2026, 9, 16))
        self.assertEqual(repeated["created"], 0)
        self.assertEqual(Task.objects.count(), 1)
