"""Exercise the real upgrade and rollback with populated historical tables."""
from datetime import date
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class UnifiedMigrationTests(TransactionTestCase):
    migrate_from = [('accounts','0005_userprofile_organizations'),
        ('core','0012_sitesettings_default_tpa_organization'),
        ('tickets','0008_supportgroup_organizations'),('tpa','0014_merge_20260930_1202')]
    migrate_to = [('accounts','0006_organizationtype_remove_userprofile_organizations_and_more'),
        ('core','0013_alter_sitesettings_default_processing_organization'),
        ('tickets','0009_ticketorganization_ticketsequence_tickettaggeduser_and_more'),
        ('tpa','0016_unified_workflow_backfill')]

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def test_populated_upgrade_preserves_ids_links_permissions_and_rollback(self):
        old = self.migrate(self.migrate_from)
        try:
            User, Profile = old.get_model('auth','User'), old.get_model('accounts','UserProfile')
            Legacy = old.get_model('tpa','TPAOrganization')
            Organization = Legacy.objects.create(code='MIG-OWNER', name_en='Migrated owner', organization_type='CORPORATE')
            insurer = Legacy.objects.create(code='MIG-INSURER', name_en='Migrated insurer', organization_type='INSURER')
            processor = Legacy.objects.create(code='MIG-PROCESS', name_en='Migrated processor', organization_type='TPA')
            user = User.objects.create(username='migration-owner', is_active=True)
            profile = Profile.objects.create(user=user)
            profile.organizations.add(Organization, processor)
            Group = old.get_model('tickets','SupportGroup')
            group = Group.objects.create(name='Migration routing', code='migration-routing')
            group.organizations.add(Organization, processor)
            group.members.add(user)
            old.get_model('core','SiteSettings').objects.update_or_create(pk=1, defaults={'default_tpa_organization':processor})
            project = old.get_model('tickets','Project').objects.create(code='TPA', name_en='Legacy processing')
            project.groups.add(group)
            product = old.get_model('tickets','Product').objects.create(project=project, code='MEDICAL', name_en='Medical')
            category = old.get_model('tickets','Category').objects.create(product=product, code='member-addition', name_en='Addition', default_group=group)
            ticket = old.get_model('tickets','Ticket').objects.create(reference='TPA-2025-000042', requester=user,
                project=project, product=product, category=category, subject='Historic request', description='Evidence')
            ticket.groups.add(group)
            comment = old.get_model('tickets','TicketComment').objects.create(ticket=ticket, author=user, body='Historic comment')
            attachment = old.get_model('tickets','TicketAttachment').objects.create(ticket=ticket, comment=comment,
                uploaded_by=user, file='tickets/evidence.pdf', original_name='evidence.pdf', content_type='application/pdf', size=123)
            policy = old.get_model('tpa','Policy').objects.create(sponsor=Organization, insurance_company=insurer,
                tpa_organization=processor, policy_number='MIG-POLICY', start_date=date(2025,1,1), expiry_date=date(2025,12,31))
            access = old.get_model('tpa','PolicyAccess').objects.create(organization=Organization, policy=policy, user=user, can_view=True, can_create_endorsement=True)
            Tx = old.get_model('tpa','MemberTransaction')
            common = dict(sponsor=Organization, insurer=insurer, policy=policy, requester=user,
                requester_organization=Organization, effective_date=date(2025,7,1), transaction_type='MEMBER_ADD')
            tx = Tx.objects.create(reference='TPA-END-2025-000010', ticket=ticket, **common)
            orphan = Tx.objects.create(reference='TPA-END-2025-000011', **common)
            row = old.get_model('tpa','MemberAction').objects.create(transaction=tx, row_number=1, action='MEMBER_ADD', corrected_data={'employee_id':'00001'})
            document = old.get_model('tpa','SourceDocument').objects.create(transaction=tx, file='sources/member.xlsx', original_name='member.xlsx')
            email = old.get_model('tpa','InboundEmail').objects.create(provider='manual', provider_message_id='migration-email',
                sender='hr@example.test', subject='Historic evidence', received_at=timezone.now(), transaction=tx)
            ct,_ = old.get_model('contenttypes','ContentType').objects.get_or_create(app_label='tpa', model='tpaorganization')
            permission,_ = old.get_model('auth','Permission').objects.get_or_create(content_type=ct, codename='change_tpaorganization', defaults={'name':'Can change organization'})
            auth_group = old.get_model('auth','Group').objects.create(name='Migration administrators')
            user.user_permissions.add(permission)
            auth_group.permissions.add(permission)

            new = self.migrate(self.migrate_to)
            Master = new.get_model('accounts','Organization')
            self.assertEqual(Master.objects.get(pk=Organization.pk).code, 'MIG-OWNER')
            self.assertEqual(Master.objects.get(pk=Organization.pk).created_at, Organization.created_at)
            self.assertEqual(set(new.get_model('accounts','UserProfile').objects.get(pk=profile.pk).organizations.values_list('pk',flat=True)), {Organization.pk,processor.pk})
            self.assertEqual(set(new.get_model('tickets','SupportGroup').objects.get(pk=group.pk).organizations.values_list('pk',flat=True)), {Organization.pk,processor.pk})
            moved_policy = new.get_model('tpa','Policy').objects.get(pk=policy.pk)
            self.assertEqual(moved_policy.organization_id, Organization.pk)
            self.assertTrue(moved_policy.workflow_organizations.filter(pk=processor.pk).exists())
            self.assertEqual(new.get_model('core','SiteSettings').objects.get(pk=1).default_processing_organization_id, processor.pk)
            moved_ticket = new.get_model('tickets','Ticket').objects.get(pk=ticket.pk)
            self.assertEqual(moved_ticket.reference, ticket.reference)
            self.assertEqual(moved_ticket.project.code, 'ADD')
            self.assertEqual(moved_ticket.policy_id, policy.pk)
            self.assertEqual(new.get_model('tickets','TicketComment').objects.get(pk=comment.pk).ticket_id, ticket.pk)
            self.assertEqual(new.get_model('tickets','TicketAttachment').objects.get(pk=attachment.pk).file.name, attachment.file.name)
            self.assertEqual(new.get_model('tpa','PolicyAccess').objects.get(pk=access.pk).policy_id, policy.pk)
            self.assertEqual(new.get_model('tpa','MemberAction').objects.get(pk=row.pk).corrected_data, row.corrected_data)
            self.assertEqual(new.get_model('tpa','SourceDocument').objects.get(pk=document.pk).file.name, document.file.name)
            moved_tx = new.get_model('tpa','MemberTransaction').objects.get(pk=tx.pk)
            self.assertEqual(moved_tx.reference, tx.reference)
            self.assertEqual(moved_tx.ticket_id, ticket.pk)
            migrated_orphan = new.get_model('tpa','MemberTransaction').objects.get(pk=orphan.pk)
            self.assertIsNotNone(migrated_orphan.ticket_id)
            self.assertEqual(migrated_orphan.reference, orphan.reference)
            self.assertTrue(migrated_orphan.ticket.reference.startswith('ADD-'))
            self.assertEqual(new.get_model('tpa','InboundEmail').objects.get(pk=email.pk).ticket_id, ticket.pk)
            self.assertEqual(new.get_model('tickets','TicketSequence').objects.get(prefix='TPA',year=2025).value, 42)
            copied = new.get_model('auth','Permission').objects.get(content_type__app_label='accounts',codename='change_organization')
            self.assertTrue(new.get_model('auth','User').objects.get(pk=user.pk).user_permissions.filter(pk=copied.pk).exists())
            self.assertTrue(new.get_model('auth','Group').objects.get(pk=auth_group.pk).permissions.filter(pk=copied.pk).exists())

            rolled_back = self.migrate(self.migrate_from)
            restored = rolled_back.get_model('tpa','TPAOrganization').objects.get(pk=Organization.pk)
            self.assertEqual(restored.code, Organization.code)
            self.assertEqual(rolled_back.get_model('tpa','Policy').objects.get(pk=policy.pk).sponsor_id, Organization.pk)
            self.assertEqual(set(rolled_back.get_model('accounts','UserProfile').objects.get(pk=profile.pk).organizations.values_list('pk',flat=True)), {Organization.pk,processor.pk})
        finally:
            self.migrate(self.migrate_to)
