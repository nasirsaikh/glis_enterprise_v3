import json
import tempfile
from datetime import date
from unittest.mock import patch

import httpx
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings

from apps.ai.models import AIProviderConfig
from apps.ai.runtime import _json_from_text, generate_json, generate_text
from .models import MemberTransaction, Policy, SourceDocument, TPAOrganization
from .services.document_intake import process_source_bundle
from .services.email_evidence import member_rows_from_html, read_email_evidence
from .services.extraction import normalize_ai_payload, select_provider
from .services.schemas import merge_recovered_payload


TABLE = """<table><tr><td>employee_id</td><td>first_name</td><td>middle_name</td><td>last_name</td><td>date_of_birth</td><td>gender</td><td>relationship</td><td>plan_code</td></tr><tr><td>00012</td><td>Sam</td><td></td><td>Example</td><td>01/02/1990</td><td>Male</td><td>PRINCIPAL</td><td>GOLD</td></tr></table>"""


class OllamaRuntimeTests(SimpleTestCase):
    def test_arrays_fences_and_reasoning_preserve_all_records(self):
        for content in ('[{"employee_id":"001"},{"employee_id":"002"}]', '```json\n[{"employee_id":"001"},{"employee_id":"002"}]\n```', '<think>ignore {examples}</think> [{"employee_id":"001"},{"employee_id":"002"}]'):
            self.assertEqual(len(_json_from_text(content)), 2)

    def test_truncated_outer_payload_is_not_replaced_with_an_inner_member(self):
        with self.assertRaises(ValueError):
            _json_from_text('{"members":[{"employee_id":"001"}')

    @patch("apps.ai.runtime.httpx.Client")
    def test_schema_grammar_failure_retries_json_and_preserves_schema_prompt(self, factory):
        client = factory.return_value.__enter__.return_value
        client.post.side_effect = [httpx.Response(500, json={"error": "failed to compile grammar"}), httpx.Response(200, json={"message": {"content": '{"members":[]}'}})]
        config = AIProviderConfig(provider="ollama", model_name="text-model")
        self.assertEqual(generate_json(config, system_prompt="Map", user_prompt="Data", response_schema={"type":"object"})[0], {"members":[]})
        self.assertEqual(client.post.call_args_list[1].kwargs["json"]["format"], "json")
        self.assertIn("schema", client.post.call_args_list[1].kwargs["json"]["messages"][0]["content"])

    @patch("apps.ai.runtime.httpx.Client")
    def test_vision_uses_chat_and_releases_ocr_model_without_json_grammar(self, factory):
        client = factory.return_value.__enter__.return_value
        client.post.return_value = httpx.Response(200, json={"message":{"content":"Readable OCR"}})
        config = AIProviderConfig(provider="ollama", model_name="glm-ocr")
        self.assertEqual(generate_text(config, system_prompt="", user_prompt="Text Recognition:", images=[{"bytes":b"image","mime_type":"image/png"}])[0], "Readable OCR")
        call = client.post.call_args
        self.assertTrue(call.args[0].endswith("/api/chat"))
        self.assertEqual(call.kwargs["json"]["keep_alive"], 0)
        self.assertNotIn("format", call.kwargs["json"])
        self.assertEqual(len(call.kwargs["json"]["messages"]), 1)

    @patch("apps.ai.runtime.httpx.Client")
    def test_vision_error_includes_actual_ollama_error(self, factory):
        factory.return_value.__enter__.return_value.post.return_value = httpx.Response(500, json={"error":"prediction aborted, token repeat limit reached"})
        with self.assertRaisesRegex(RuntimeError, "token repeat limit reached"):
            generate_text(AIProviderConfig(provider="ollama", model_name="glm-ocr"), system_prompt="", user_prompt="Text Recognition:", images=[{"bytes":b"image","mime_type":"image/png"}])

    def test_empty_pydantic_placeholder_cannot_block_recovered_member(self):
        original = {"members":[{"full_name":None,"date_of_birth":None,"confidence":0}]}
        self.assertEqual(normalize_ai_payload(original)["members"], [])
        recovered = {"members":[{"full_name":"Sam Example","date_of_birth":"1990-02-01"}]}
        self.assertEqual(merge_recovered_payload(original, recovered)["members"], recovered["members"])

    def test_html_member_table_preserves_blank_cells_and_leading_zeroes(self):
        row = member_rows_from_html(TABLE)[0]
        self.assertEqual(row["employee_id"], "00012")
        self.assertEqual(row["middle_name"], "")
        self.assertEqual(row["last_name"], "Example")

    def test_eml_body_and_attachment_are_read_separately(self):
        content = b'From: sender@example.test\nTo: intake@example.test\nSubject: Addition\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary="B"\n\n--B\nContent-Type: text/plain\n\nPolicy: TEST-1\n--B\nContent-Type: text/csv\nContent-Disposition: attachment; filename="members.csv"\n\nemployee_id,first_name,last_name\n00012,Sam,Example\n--B--\n'
        data = read_email_evidence("sample.eml", content)
        self.assertIn("Policy: TEST-1", data["body_text"])
        self.assertEqual(data["attachments"][0]["name"], "members.csv")


class OCRRecoveryTests(TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        media=override_settings(MEDIA_ROOT=directory.name);media.enable();self.addCleanup(media.disable)

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        cls.actor = get_user_model().objects.create_superuser("ocr-admin", "ocr@example.test", "test")
        sponsor = TPAOrganization.objects.create(code="OCR-SP", name_en="Sponsor", organization_type="CORPORATE")
        insurer = TPAOrganization.objects.create(code="OCR-IN", name_en="Insurer", organization_type="INSURER")
        policy = Policy.objects.create(sponsor=sponsor, insurance_company=insurer, policy_number="OCR-1", start_date=date(2026,1,1), expiry_date=date(2026,12,31))
        cls.tx = MemberTransaction.objects.create(policy=policy,sponsor=sponsor,insurer=insurer,requester=cls.actor,requester_organization=sponsor,transaction_type="MEMBER_ADD",effective_date=date(2026,7,1))
        cls.provider = AIProviderConfig.objects.create(name="Text",provider="mock",model_name="text-model",task_capabilities=["email_extraction","member_field_mapping"],allow_sensitive_data=True)

    def test_text_provider_selection_excludes_ocr_even_when_misconfigured(self):
        AIProviderConfig.objects.create(name="OCR", provider="ollama", model_name="glm-ocr:latest", supports_vision=False, priority=1, task_capabilities=["email_extraction","member_field_mapping"],allow_sensitive_data=True)
        self.assertEqual(select_provider(vision=False, sensitive=True, capability="email_extraction"), self.provider)

    @patch("apps.tpa.services.document_intake._map_evidence_text")
    @patch("apps.tpa.services.document_intake.docling_text", return_value="Sam Example DOB 01/02/1990")
    @patch("apps.tpa.services.document_intake._ocr_image", side_effect=RuntimeError("Ollama HTTP 500: runner stopped"))
    def test_vision_500_and_empty_initial_mapping_recover_populated_form_fields(self, ocr, recovery, mapper):
        row = {"employee_id":"0012","first_name":"Sam","last_name":"Example","date_of_birth":"1990-02-01","gender":"Male","relationship":"PRINCIPAL","plan_code":"GOLD"}
        mapper.side_effect = [({"members":[{"full_name":None}]},self.provider,None,1),({"members":[row]},self.provider,None,1)]
        document = SourceDocument.objects.create(transaction=self.tx, original_name="id.png",file=SimpleUploadedFile("id.png",b"fixture"))
        actions = process_source_bundle(self.tx,[document],actor=self.actor)
        self.assertEqual(actions[0].corrected_data["date_of_birth"],"1990-02-01")
        document.refresh_from_db()
        self.assertEqual(document.processing_state,SourceDocument.State.PROCESSED)
        self.assertEqual(document.extraction_method,"LOCAL_OCR_RECOVERY")
        recovery.assert_called_once()

    def test_canonical_email_table_fills_member_without_ai_mapping(self):
        from email.message import EmailMessage
        message=EmailMessage();message["Subject"]="Addition";message.set_content("Member table attached below");message.add_alternative(TABLE,subtype="html")
        document=SourceDocument.objects.create(transaction=self.tx,original_name="request.eml",file=SimpleUploadedFile("request.eml",message.as_bytes()))
        with patch("apps.tpa.services.document_intake._map_evidence_text") as mapper:
            actions=process_source_bundle(self.tx,[document],actor=self.actor)
        mapper.assert_not_called()
        self.assertEqual(actions[0].corrected_data["employee_id"],"00012")
        self.assertEqual(actions[0].corrected_data["date_of_birth"],"1990-02-01")
