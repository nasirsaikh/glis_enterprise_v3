"""Real row-lock races, exercised on the production database engine."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from services.ticket_participants import take_over_ticket
from .models import Category, Product, Project, SupportGroup, Ticket


@skipUnlessDBFeature('has_select_for_update')
class WorkflowConcurrencyTests(TransactionTestCase):
    def setUp(self):
        User = get_user_model()
        self.users = [User.objects.create_user(f'race-user-{n}') for n in range(2)]
        self.project = Project.objects.create(code='RACE', name_en='Race checks')
        self.product = Product.objects.create(project=self.project, code='RACE', name_en='Race')
        self.category = Category.objects.create(product=self.product, code='RACE', name_en='Race',send_initial_email=False,send_update_email=False)
        self.group = SupportGroup.objects.create(code='race-team',name='Race team')
        self.group.members.add(*self.users)

    def ticket(self):
        return Ticket.objects.create(project=self.project, product=self.product, category=self.category,
            requester=self.users[0], subject='Race', description='Race')

    def test_simultaneous_reference_allocation_is_unique(self):
        barrier = Barrier(2)
        def allocate(_):
            close_old_connections()
            try:
                barrier.wait(timeout=20)
                return self.ticket().reference
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            references=list(pool.map(allocate,range(2)))
        self.assertEqual(len(set(references)),2)
        self.assertEqual(Ticket.objects.filter(project=self.project).count(),2)

    def test_only_one_simultaneous_takeover_succeeds(self):
        ticket = self.ticket()
        ticket.groups.add(self.group)
        barrier = Barrier(2)
        def take(user):
            close_old_connections()
            try:
                fresh=Ticket.objects.get(pk=ticket.pk)
                barrier.wait(timeout=20)
                try:
                    take_over_ticket(fresh,user)
                    return 'taken'
                except ValueError:return 'conflict'
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(take,self.users))
        self.assertCountEqual(outcomes,['taken','conflict'])
        ticket.refresh_from_db()
        self.assertEqual(ticket.assignees.count(),1)
        self.assertEqual(ticket.events.filter(event_type='takeover').count(),1)
