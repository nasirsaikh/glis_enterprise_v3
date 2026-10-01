from datetime import date, datetime, timedelta, timezone as utc_timezone
from unittest.mock import patch
import io

from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from PIL import Image

from apps.ai.models import AIProviderConfig
from .models import BenefitPlan, InboundEmail, Policy, TPAOrganization
from .services.ai_intake import extract_email_payload, process_inbound_email, _recover_explicit_email_header
from .services.email_evidence import html_to_text
from .services.document_fallback import docling_text, _easyocr_text
from .test_ocr_regressions import TABLE


class ExplicitEmailHeaderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor=get_user_model().objects.create_superuser("header-admin","header@example.test","test")
        sponsor=TPAOrganization.objects.create(code="HDR-SP",name_en="Sponsor",organization_type="CORPORATE")
        insurer=TPAOrganization.objects.create(code="HDR-IN",name_en="Insurer",organization_type="INSURER")
        cls.policy=Policy.objects.create(sponsor=sponsor,insurance_company=insurer,policy_number="P/900/2026/0001",
            status="active",start_date=date(2026,1,1),expiry_date=date(2026,12,31),initial_enrollment_completed_at=timezone.now(),allowed_backdating_days=3650)
        BenefitPlan.objects.create(policy=cls.policy,code="GOLD",name="Gold",annual_premium=100)
        cls.provider=AIProviderConfig.objects.create(name="Header text",provider="mock",model_name="text",
            task_capabilities=["email_extraction","member_field_mapping"],allow_sensitive_data=True)

    def setUp(self):
        self.email=InboundEmail.objects.create(provider="test",provider_message_id="header-test",
            sender="hr@example.test",recipient="intake@example.test",
            received_at=datetime(2026,7,1,23,0,tzinfo=utc_timezone.utc),
            subject=f"FW: Addition for {self.policy.policy_number}",
            body_text="legacy flattened text",body_html=f"<p>Addition effective from tomorrow for policy number {self.policy.policy_number}</p>{TABLE}")

    @patch("apps.tpa.services.ai_intake.generate_json")
    def test_member_only_model_output_recovers_policy_type_and_relative_date(self,generate):
        generate.return_value=({"members":[{"first_name":"Sam"}],"confidence":0},1)
        payload,_,_,raw=extract_email_payload(self.email,self.actor)
        self.assertEqual(payload["policy_number"],self.policy.policy_number)
        self.assertEqual(payload["classification"],"MEMBER_ADD")
        self.assertEqual(payload["classification_source"],"EXPLICIT_EMAIL_HEADER")
        self.assertEqual(payload["effective_date"],(timezone.localdate(self.email.received_at)+timedelta(days=1)).isoformat())
        self.assertEqual(payload["members"][0]["employee_id"],"00012")
        self.assertIsNone(raw.get("policy_number"))
        prompt=generate.call_args.kwargs["user_prompt"]
        self.assertIn("Policy",prompt)
        self.assertNotIn("&nbsp;",prompt)

    @patch("apps.tpa.services.ai_intake.generate_json",return_value=({"members":[],"confidence":0},1))
    @patch("apps.tpa.services.ai_intake.sender_is_authorized",return_value=(True,None,""))
    def test_explicit_header_creates_endorsement_without_lowering_ai_threshold(self,authority,generate):
        tx=process_inbound_email(self.email,self.actor)
        self.assertIsNotNone(tx)
        self.assertEqual(tx.policy_id,self.policy.pk)
        self.assertEqual(tx.member_actions.count(),1)
        self.assertEqual(tx.member_actions.first().corrected_data["date_of_birth"],"1990-02-01")
        authority.assert_called_once()

    @patch("apps.tpa.services.ai_intake.generate_json",return_value=({"members":[],"confidence":0},1))
    @patch("apps.tpa.services.ai_intake.sender_is_authorized",return_value=(False,None,"Sender not authorized"))
    def test_header_recovery_never_bypasses_sender_authority(self,authority,generate):
        self.assertIsNone(process_inbound_email(self.email,self.actor))
        self.email.refresh_from_db()
        self.assertEqual(self.email.processing_state,"UNAUTHORIZED")
        self.assertEqual(self.email.processing_stage,"SENDER_AUTHORITY")

    def test_complete_low_confidence_ai_header_still_requires_review(self):
        payload={"is_endorsement_request":True,"policy_number":self.policy.policy_number,
                 "transaction_type":"MEMBER_ADD","classification":"MEMBER_ADD","confidence":0.1}
        recovered=_recover_explicit_email_header(self.email,payload,{})
        self.assertNotIn("classification_source",recovered)

    def test_negative_conditional_and_ambiguous_requests_are_not_reclassified(self):
        for text in ("Do not process addition", "If addition is required", "Addition and deletion"):
            self.email.subject=f"{text} for {self.policy.policy_number}";self.email.body_html=""
            self.assertNotIn("classification_source",_recover_explicit_email_header(self.email,{"members":[]},{}))

    def test_multiple_policies_and_conflicting_ai_type_stay_for_review(self):
        Policy.objects.create(sponsor=self.policy.sponsor,insurance_company=self.policy.insurance_company,
            policy_number="P/900/2026/0002",status="active",start_date=date(2026,1,1),expiry_date=date(2026,12,31))
        self.email.subject += " and P/900/2026/0002"
        self.assertNotIn("classification_source",_recover_explicit_email_header(self.email,{"members":[]},{}))
        self.email.subject="Addition";self.email.body_html=f"<p>Addition for {self.policy.policy_number}</p>"
        self.assertNotIn("classification_source",_recover_explicit_email_header(self.email,{"classification":"MEMBER_DELETE"},{}))


class LocalOCRFallbackTests(SimpleTestCase):
    def test_html_text_preserves_cells_paragraphs_and_decodes_entities(self):
        value=html_to_text("<style>hidden</style><p>Addition&nbsp;tomorrow</p>"+TABLE)
        self.assertIn("Addition tomorrow\nemployee_id | first_name",value)
        self.assertIn("00012 | Sam |",value)
        self.assertNotIn("hidden",value)

    @patch("apps.tpa.services.document_fallback._docling_text",side_effect=RuntimeError("Layout models unavailable"))
    @patch("apps.tpa.services.document_fallback._easyocr_text",return_value="Recovered ID text")
    @patch("apps.tpa.services.document_fallback._tesseract_text")
    def test_direct_easyocr_recovers_when_docling_layout_models_fail(self,tesseract,easy,docling):
        self.assertEqual(docling_text("id.png",b"fixture"),"Recovered ID text")
        tesseract.assert_not_called()

    @patch("apps.tpa.services.document_fallback._easyocr_reader")
    def test_direct_easyocr_checks_rotated_small_id_text(self,factory):
        output=io.BytesIO();Image.new("RGB",(120,80),"white").save(output,format="PNG")
        factory.return_value.readtext.return_value=["Name: Sam Example","DOB: 01/02/1990"]
        result=_easyocr_text("id.png",output.getvalue())
        self.assertIn("Sam Example",result)
        call=factory.return_value.readtext.call_args
        self.assertEqual(call.kwargs["rotation_info"],[90,180,270])
        self.assertEqual(call.args[0].shape[1],1400)

    @override_settings(TPA_OCR_ENGINE="local")
    @patch("apps.tpa.services.document_intake.docling_text",return_value="Local ID text")
    @patch("apps.tpa.services.document_intake.generate_text")
    def test_local_mode_never_calls_ollama_vision(self,vision,local):
        from .services.document_intake import _ocr_image
        self.assertEqual(_ocr_image(None,b"image","image/png")[0],"Local ID text")
        vision.assert_not_called()

    @patch("apps.tpa.services.document_fallback._docling_text",side_effect=RuntimeError("docling missing"))
    @patch("apps.tpa.services.document_fallback._easyocr_text",side_effect=RuntimeError("easyocr missing"))
    @patch("apps.tpa.services.document_fallback._tesseract_text",side_effect=RuntimeError("tesseract missing"))
    def test_failed_recovery_exposes_each_backend_error(self,*mocks):
        with self.assertRaisesRegex(RuntimeError,"Docling: docling missing; EasyOCR: easyocr missing; Tesseract: tesseract missing"):
            docling_text("id.png",b"fixture")
