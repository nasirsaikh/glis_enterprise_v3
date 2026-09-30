import tempfile
from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings

from apps.ai.models import AIProviderConfig
from apps.ai.runtime import generate_json
from .models import MemberTransaction, Policy, SourceDocument, TPAOrganization
from .services.document_intake import process_source_bundle
from .services.extraction import normalize_ai_payload
from .services.schemas import MemberBundle, merge_recovered_payload, missing_member_fields


class ExtractionContractTests(SimpleTestCase):
    def test_identifiers_and_dates_are_normalized_without_losing_leading_zeroes(self):
        payload = normalize_ai_payload({"members": [{
            "national_id": "001234", "date_of_birth": "01/02/1990",
            "full_name": "Jane Doe", "gender": "F", "relationship": "SELF",
        }]})
        member = payload["members"][0]
        self.assertEqual(member["national_id"], "001234")
        self.assertEqual(member["date_of_birth"], "1990-02-01")
        self.assertEqual(member["first_name"], "Jane")
        self.assertEqual(member["gender"], "Female")
        self.assertEqual(member["relationship"], "PRINCIPAL")

    def test_nested_member_values_and_invalid_bundles_are_rejected(self):
        for payload in (
            {"members": [{"national_id": {"value": "123"}}]},
            {"members": [{"Employee ID": ["123"]}]},
            {"members": "not an array"},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                normalize_ai_payload(payload)

    @patch("apps.ai.runtime.httpx.Client")
    def test_ollama_receives_pydantic_json_schema(self, client_factory):
        config = AIProviderConfig(name="Schema", provider="ollama", model_name="qwen2.5:7b")
        response = MagicMock()
        response.json.return_value = {"message": {"content": '{"members":[]}'}}
        client = client_factory.return_value.__enter__.return_value
        client.post.return_value = response
        generate_json(config, system_prompt="Map members", user_prompt="Evidence",
                      response_schema=MemberBundle.model_json_schema())
        self.assertEqual(client.post.call_args.kwargs["json"]["format"], MemberBundle.model_json_schema())

    def test_conflicting_recovery_identifiers_preserve_original_member(self):
        original = {"members": [{"national_id": "001", "passport_number": "P1"}]}
        recovered = {"members": [{"national_id": "001", "passport_number": "P2", "date_of_birth": "1990-01-01"}]}
        merged = merge_recovered_payload(original, recovered)
        self.assertEqual(merged["members"][0]["passport_number"], "P1")
        self.assertNotIn("date_of_birth", merged["members"][0])
        self.assertTrue(merged["warnings"])

    def test_existing_member_endorsements_require_identity_only(self):
        self.assertEqual(missing_member_fields({"members": [{"card_number": "001"}]}, "MEMBER_DELETE"), [])
        self.assertEqual(missing_member_fields({"members": []}, "POLICY_CANCEL"), [])
        self.assertTrue(missing_member_fields({"members": [{"card_number": "001"}]}, "MEMBER_ADD"))


class DocumentRecoveryTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)
        self.actor = get_user_model().objects.create_superuser("recovery-admin", "recovery@example.com", "test")
        sponsor = TPAOrganization.objects.create(code="REC-SP", name_en="Recovery sponsor", organization_type="CORPORATE")
        insurer = TPAOrganization.objects.create(code="REC-IN", name_en="Recovery insurer", organization_type="INSURER")
        policy = Policy.objects.create(sponsor=sponsor, insurance_company=insurer, policy_number="REC-1",
                                      start_date=date(2026, 1, 1), expiry_date=date(2026, 12, 31))
        self.tx = MemberTransaction.objects.create(sponsor=sponsor, insurer=insurer, policy=policy,
            transaction_type=MemberTransaction.Type.MEMBER_ADD, effective_date=date(2026, 1, 1), requester=self.actor, requester_organization=sponsor)
        self.provider = AIProviderConfig.objects.create(name="Recovery mapper", provider="mock", allow_sensitive_data=True)
        self.document = SourceDocument.objects.create(transaction=self.tx, original_name="member.pdf",
            content_type="application/pdf", file=SimpleUploadedFile("member.pdf", b"%PDF-test", content_type="application/pdf"))
        self.partial = {"members": [{"employee_id": "001", "national_id": "001234", "first_name": "Jane", "last_name": "Doe"}]}

    @patch("apps.tpa.services.document_intake.docling_text", return_value="Recovered birth date and plan")
    @patch("apps.tpa.services.document_intake._map_evidence_text")
    @patch("apps.tpa.services.document_intake._pdf_text_or_ocr", return_value=("Member evidence", "PDF_TEXT", 1))
    def test_incomplete_mapping_recovers_missing_fields_once(self, native, mapper, fallback):
        repaired = {"members": [{"employee_id": "001", "national_id": "001234", "first_name": "Changed",
            "date_of_birth": "1990-01-01", "gender": "Female", "relationship": "PRINCIPAL", "plan_code": "GOLD"}]}
        mapper.side_effect = [(self.partial, self.provider, None, 1), (repaired, self.provider, None, 1)]
        actions = process_source_bundle(self.tx, [self.document], actor=self.actor)
        fallback.assert_called_once()
        self.assertEqual(mapper.call_count, 2)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].corrected_data["first_name"], "Jane")
        self.assertEqual(actions[0].corrected_data["national_id"], "001234")
        self.assertEqual(actions[0].corrected_data["date_of_birth"], "1990-01-01")
        self.document.refresh_from_db()
        self.assertEqual(self.document.extraction_method, "DOCLING_RECOVERY")
        self.assertEqual(self.document.processing_state, SourceDocument.State.PROCESSED)

    @patch("apps.tpa.services.document_intake.docling_text", side_effect=RuntimeError("No readable text"))
    @patch("apps.tpa.services.document_intake._map_evidence_text")
    @patch("apps.tpa.services.document_intake._pdf_text_or_ocr", return_value=("Member evidence", "PDF_TEXT", 1))
    def test_failed_recovery_keeps_missing_fields_for_review(self, native, mapper, fallback):
        mapper.return_value = (self.partial, self.provider, None, 1)
        actions = process_source_bundle(self.tx, [self.document], actor=self.actor)
        self.assertEqual(len(actions), 1)
        self.assertFalse(actions[0].corrected_data.get("date_of_birth"))
        self.document.refresh_from_db()
        self.assertEqual(self.document.processing_state, SourceDocument.State.REVIEW)
        self.assertIn("date_of_birth", self.document.processing_error)
        self.assertIn("No readable text", self.document.processing_error)
