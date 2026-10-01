import json
import hashlib
import tempfile
from datetime import date
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.ai.models import AIProviderConfig
from apps.job_center.models import QueuedJob
from apps.job_center.jobs.tpa_jobs import reprocess_tpa_inbound_email
from apps.job_center.services.queue_worker import claim_next_job, execute_queued_job
from .models import InboundEmail, InboundEmailAttachment, MemberAction, MemberTransaction, Policy, SourceDocument, TPAOrganization
from .services.ai_intake import extract_email_payload, process_inbound_email, _add_ai_members, _process_attachments
from .services.email_reprocessing import REPROCESS_QUEUED, queue_email_reprocessing
from .test_ocr_regressions import TABLE


@override_settings(JOB_CENTER_ENABLED=True)
class InboundEmailAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser("email-admin","admin@example.test","test")
        cls.staff = User.objects.create_user("email-staff",is_staff=True)
        cls.reader = User.objects.create_user("email-reader",is_staff=True)
        cls.sponsor = TPAOrganization.objects.create(code="EMA-SP",name_en="Own sponsor",organization_type="CORPORATE")
        cls.other_sponsor = TPAOrganization.objects.create(code="EMA-OTHER",name_en="Other sponsor",organization_type="CORPORATE")
        cls.insurer = TPAOrganization.objects.create(code="EMA-IN",name_en="Insurer",organization_type="INSURER")
        cls.policy = Policy.objects.create(sponsor=cls.sponsor,insurance_company=cls.insurer,policy_number="EMAIL-1",start_date=date(2026,1,1),expiry_date=date(2026,12,31),status="active",allowed_backdating_days=3650,initial_enrollment_completed_at=timezone.now())
        cls.other_policy = Policy.objects.create(sponsor=cls.other_sponsor,insurance_company=cls.insurer,policy_number="EMAIL-OTHER",start_date=date(2026,1,1),expiry_date=date(2026,12,31))
        for actor in (cls.staff,cls.reader):
            actor.profile.organizations.add(cls.sponsor)
            actor.user_permissions.add(Permission.objects.get(codename="configure_tpa"),Permission.objects.get(codename="view_inboundemail"))
        cls.staff.user_permissions.add(Permission.objects.get(codename="change_inboundemail"))
        cls.tx = MemberTransaction.objects.create(policy=cls.policy,sponsor=cls.sponsor,insurer=cls.insurer,requester=cls.admin,requester_organization=cls.sponsor,transaction_type="MEMBER_ADD",effective_date=date(2026,7,1))
        cls.other_tx = MemberTransaction.objects.create(policy=cls.other_policy,sponsor=cls.other_sponsor,insurer=cls.insurer,requester=cls.admin,requester_organization=cls.other_sponsor,transaction_type="MEMBER_ADD",effective_date=date(2026,7,1))
        cls.email = InboundEmail.objects.create(provider="manual",provider_message_id="admin-retry",created_by=cls.admin,sender="hr@example.test",recipient="intake@example.test",subject="Own email",received_at=timezone.now(),transaction=cls.tx,processing_state=InboundEmail.State.REVIEW)
        cls.other_email = InboundEmail.objects.create(provider="office365_graph",provider_message_id="admin-other",sender="other@example.test",recipient="intake@example.test",subject="Foreign email",received_at=timezone.now(),transaction=cls.other_tx)
        cls.provider = AIProviderConfig.objects.create(name="Email text",provider="mock",model_name="text-model",allow_sensitive_data=True,task_capabilities=["email_extraction"])

    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        media=override_settings(MEDIA_ROOT=directory.name);media.enable();self.addCleanup(media.disable)
        self.client.force_login(self.admin)

    def bulk(self, emails):
        return self.client.post(reverse("admin:tpa_inboundemail_changelist"),{"action":"reprocess_selected_emails","_selected_action":[email.pk for email in emails]},follow=True)

    def payload(self):
        return {"is_endorsement_request":True,"classification":"MEMBER_ADD","transaction_type":"MEMBER_ADD","policy_number":self.policy.policy_number,"confidence":None,"members":[{"employee_id":"0012","first_name":"Sam","last_name":"Example","date_of_birth":"1990-02-01","gender":"Male","relationship":"PRINCIPAL","plan_code":"GOLD"}]}

    def test_bulk_admin_action_queues_and_audits_without_blocking_on_ai(self):
        with patch("apps.tpa.services.ai_intake.generate_json") as generate:
            response=self.bulk([self.email])
        generate.assert_not_called()
        self.assertContains(response,"queued for reprocessing")
        job=QueuedJob.objects.get()
        self.assertEqual(job.parameters,{"email_id":self.email.pk,"actor_id":self.admin.pk})
        self.email.refresh_from_db()
        self.assertEqual(self.email.processing_stage,REPROCESS_QUEUED)
        self.assertTrue(LogEntry.objects.filter(object_id=str(self.email.pk),change_message__contains="Queued email reprocessing").exists())

    def change_data(self):
        url=reverse("admin:tpa_inboundemail_change",args=[self.email.pk])
        response=self.client.get(url)
        self.assertContains(response,'name="_reprocess"')
        form=response.context["adminform"].form
        data={key:json.dumps(value) if isinstance(value,(dict,list)) else value for key,value in form.initial.items()}
        received=self.email.received_at
        data.pop("received_at",None)
        data.update({"received_at_0":received.strftime("%Y-%m-%d"),"received_at_1":received.strftime("%H:%M:%S"),"body_text":"Updated evidence","_reprocess":"1","attachments-TOTAL_FORMS":"0","attachments-INITIAL_FORMS":"0","attachments-MIN_NUM_FORMS":"0","attachments-MAX_NUM_FORMS":"1000"})
        return url,data

    def test_single_email_save_and_reprocess_saves_edits_before_queueing(self):
        url,data=self.change_data()
        response=self.client.post(url,data)
        self.assertEqual(response.status_code,302)
        self.email.refresh_from_db()
        self.assertEqual(self.email.body_text,"Updated evidence")
        self.assertEqual(QueuedJob.objects.count(),1)

    def test_save_and_reprocess_hashes_new_admin_attachments(self):
        url,data=self.change_data()
        data.update({"attachments-TOTAL_FORMS":"1","attachments-0-original_name":"id.png","attachments-0-file":SimpleUploadedFile("id.png",b"fixture",content_type="image/png")})
        response=self.client.post(url,data)
        self.assertEqual(response.status_code,302)
        attachment=self.email.attachments.get()
        self.assertEqual(attachment.sha256,hashlib.sha256(b"fixture").hexdigest())
        self.assertEqual(attachment.size,len(b"fixture"))
        self.assertEqual(QueuedJob.objects.count(),1)

    def test_duplicate_click_does_not_queue_twice_and_cancelled_job_can_be_retried(self):
        job=queue_email_reprocessing(self.email,self.admin)
        with self.assertRaisesRegex(ValueError,"already queued"):
            queue_email_reprocessing(self.email,self.admin)
        job.status=QueuedJob.Status.CANCELLED;job.save(update_fields=["status"])
        queue_email_reprocessing(self.email,self.admin)
        self.assertEqual(QueuedJob.objects.count(),2)

    def test_completed_endorsement_and_running_email_are_protected(self):
        self.tx.status=MemberTransaction.Status.COMPLETED;self.tx.save(update_fields=["status"])
        with self.assertRaisesRegex(ValueError,"left intake"):
            queue_email_reprocessing(self.email,self.admin)
        self.tx.status=MemberTransaction.Status.DRAFT;self.tx.save(update_fields=["status"])
        self.email.processing_state=InboundEmail.State.PROCESSING;self.email.save(update_fields=["processing_state"])
        with self.assertRaisesRegex(ValueError,"already being processed"):
            queue_email_reprocessing(self.email,self.admin)
        self.assertFalse(QueuedJob.objects.exists())

    def test_staff_cannot_see_or_reprocess_another_organization(self):
        self.client.force_login(self.staff)
        response=self.bulk([self.email,self.other_email])
        self.assertNotContains(response,"Foreign email")
        self.assertEqual(QueuedJob.objects.count(),1)
        self.assertEqual(QueuedJob.objects.get().parameters["email_id"],self.email.pk)
        with self.assertRaises(PermissionDenied):
            queue_email_reprocessing(self.other_email,self.staff)

    def test_read_only_staff_cannot_queue(self):
        with self.assertRaises(PermissionDenied):
            queue_email_reprocessing(self.email,self.reader)
        self.client.force_login(self.reader)
        response=self.client.get(reverse("admin:tpa_inboundemail_change",args=[self.email.pk]))
        self.assertNotContains(response,'name="_reprocess"')

    def test_permissions_are_checked_again_when_queued_job_starts(self):
        job=queue_email_reprocessing(self.email,self.staff)
        self.staff.is_active=False;self.staff.save(update_fields=["is_active"])
        job=claim_next_job()
        execute_queued_job(job)
        job.refresh_from_db();self.email.refresh_from_db()
        self.assertEqual(job.status,QueuedJob.Status.FAILED)
        self.assertEqual(self.email.processing_stage,"REPROCESS_BLOCKED")
        self.assertTrue(self.email.processing_error)

    @patch("apps.tpa.services.ai_intake.generate_json")
    def test_worker_reuses_existing_endorsement_and_preserves_corrections(self,generate):
        generate.return_value=(self.payload(),1)
        row=MemberAction.objects.create(transaction=self.tx,action=self.tx.transaction_type,row_number=1,corrected_data={"employee_id":"0012","first_name":"Manual","last_name":"Example"})
        job=queue_email_reprocessing(self.email,self.admin)
        execute_queued_job(job)
        self.email.refresh_from_db();row.refresh_from_db();job.refresh_from_db()
        self.assertEqual(job.status,QueuedJob.Status.SUCCESS)
        self.assertEqual(self.email.transaction_id,self.tx.pk)
        self.assertEqual(self.tx.member_actions.count(),1)
        self.assertEqual(row.corrected_data["first_name"],"Manual")
        self.assertEqual(row.corrected_data["date_of_birth"],"1990-02-01")
        self.assertTrue(self.tx.events.filter(event_type="email_reprocessed").exists())

    @patch("apps.tpa.services.ai_intake.generate_json")
    def test_email_table_maps_even_when_llm_returns_empty_member_placeholder(self,generate):
        raw=self.payload();raw["members"]=[{"full_name":None}]
        generate.return_value=(raw,1)
        self.email.body_html=TABLE;self.email.save(update_fields=["body_html"])
        payload,_,_,_=extract_email_payload(self.email,self.admin)
        self.assertEqual(payload["members"][0]["employee_id"],"00012")
        self.assertEqual(payload["members"][0]["date_of_birth"],"1990-02-01")

    def test_repeat_extraction_without_ids_matches_name_and_birth_date(self):
        payload=self.payload();payload["members"][0].pop("employee_id")
        _add_ai_members(self.tx,payload,source="email-body")
        _add_ai_members(self.tx,payload,source="email-body")
        self.assertEqual(self.tx.member_actions.count(),1)

    @patch("apps.tpa.services.ai_intake.process_source_bundle")
    @patch("apps.tpa.services.ai_intake._copy_attachment_to_ticket")
    def test_force_reprocess_rereads_cached_attachment_without_duplicate_source(self,copy,bundle):
        source=SourceDocument.objects.create(transaction=self.tx,original_name="id.png",file=SimpleUploadedFile("id.png",b"fixture"),source_hash="same-hash",processed=True,processing_state=SourceDocument.State.PROCESSED)
        attachment=InboundEmailAttachment.objects.create(inbound_email=self.email,original_name="id.png",file=SimpleUploadedFile("email-id.png",b"fixture"),sha256="same-hash",processing_state=InboundEmailAttachment.State.PROCESSED)
        def process(tx,documents,actor):
            document=documents[0];document.processed=True;document.processing_state=SourceDocument.State.PROCESSED;document.extracted_payload={"members":[{"employee_id":"0012"}]};document.save()
        bundle.side_effect=process
        _process_attachments(self.tx,self.email,self.admin,reprocess=True)
        copy.assert_not_called();bundle.assert_called_once()
        self.assertEqual(self.tx.source_documents.count(),1)
        attachment.refresh_from_db()
        self.assertEqual(attachment.extracted_payload["members"][0]["employee_id"],"0012")

    @patch("apps.tpa.services.ai_intake.generate_json")
    def test_force_cannot_mutate_completed_endorsement(self,generate):
        self.tx.status=MemberTransaction.Status.COMPLETED;self.tx.save(update_fields=["status"])
        with self.assertRaisesRegex(ValueError,"left intake"):
            process_inbound_email(self.email,self.admin,force=True)
        generate.assert_not_called()
