import os
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.ai.models import AIExtractionProfile, AIProviderConfig


class Command(BaseCommand):
    help = (
        "Configure the local Ollama providers and extraction profiles used by "
        "TPA document OCR, member mapping and inbound-email extraction."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--endpoint",
            default=os.getenv("TPA_OLLAMA_HOST")
            or os.getenv("OLLAMA_HOST")
            or "http://127.0.0.1:11434",
        )
        parser.add_argument(
            "--ocr-model",
            default=os.getenv("TPA_OLLAMA_OCR_MODEL", "glm-ocr"),
        )
        parser.add_argument(
            "--text-model",
            default=os.getenv("TPA_OLLAMA_TEXT_MODEL", "qwen2.5:7b"),
        )

    def handle(self, *args, **options):
        endpoint = options["endpoint"].rstrip("/")
        ocr_model = options["ocr_model"].strip()
        text_model = options["text_model"].strip()

        vision, _ = AIProviderConfig.objects.update_or_create(
            name="TPA Ollama Vision OCR",
            defaults={
                "provider": AIProviderConfig.Provider.OLLAMA,
                "model_name": ocr_model,
                "endpoint": endpoint,
                "secret_reference": "",
                "temperature": Decimal("0.00"),
                "timeout_seconds": 600,
                "supports_vision": True,
                "task_capabilities": ["document_extraction"],
                "runtime_options": {"keep_alive": 0, "num_ctx": 8192},
                "allow_sensitive_data": True,
                "is_active": True,
                "priority": 10,
            },
        )
        text, _ = AIProviderConfig.objects.update_or_create(
            name="TPA Ollama Text Mapping",
            defaults={
                "provider": AIProviderConfig.Provider.OLLAMA,
                "model_name": text_model,
                "endpoint": endpoint,
                "secret_reference": "",
                "temperature": Decimal("0.00"),
                "timeout_seconds": 300,
                "supports_vision": False,
                "task_capabilities": [
                    "member_field_mapping",
                    "email_extraction",
                    "structured_header_mapping",
                ],
                "runtime_options": {"keep_alive": "15m", "num_ctx": 8192},
                "allow_sensitive_data": True,
                "is_active": True,
                "priority": 20,
            },
        )

        AIExtractionProfile.objects.update_or_create(
            name="TPA Medical Vision Extraction",
            task=AIExtractionProfile.Task.DOCUMENT_EXTRACTION,
            applicable_product="MEDICAL",
            applicable_transaction_type="",
            defaults={
                "system_prompt": (
                    "Transcribe insurance member evidence faithfully. Preserve labels, "
                    "identifiers, dates, names, MRZ values and table relationships."
                ),
                "instructions": (
                    "Do not infer missing fields, eligibility, pricing, STP or approval. "
                    "Unreadable values must remain null/unknown."
                ),
                "field_aliases": {},
                "priority": 1,
                "is_active": True,
            },
        )
        AIExtractionProfile.objects.update_or_create(
            name="TPA Medical Member Mapping",
            task=AIExtractionProfile.Task.MEMBER_FIELD_MAPPING,
            applicable_product="MEDICAL",
            applicable_transaction_type="",
            defaults={
                "system_prompt": (
                    "Map OCR/document evidence to strict canonical TPA member JSON only."
                ),
                "instructions": (
                    "Combine related front/back evidence where appropriate. Use "
                    "PRINCIPAL/SPOUSE/CHILD/OTHER and YYYY-MM-DD dates. Never decide "
                    "eligibility, premium, STP or approval."
                ),
                "field_aliases": {
                    "employee_id": ["employee no", "staff id", "emp no"],
                    "national_id": ["civil id", "national id"],
                    "passport_number": ["passport", "passport no"],
                    "plan_code": ["plan", "benefit plan"],
                },
                "priority": 1,
                "is_active": True,
            },
        )
        AIExtractionProfile.objects.update_or_create(
            name="TPA Medical Email Extraction",
            task=AIExtractionProfile.Task.EMAIL_EXTRACTION,
            applicable_product="MEDICAL",
            applicable_transaction_type="",
            defaults={
                "system_prompt": (
                    "Extract only facts present in the endorsement email. Return strict "
                    "transaction/member JSON and never decide eligibility, premium, STP "
                    "or approval."
                ),
                "instructions": (
                    "Map relationships to PRINCIPAL/SPOUSE/CHILD/OTHER and dates to "
                    "YYYY-MM-DD. Use policy/type/date hints when supplied."
                ),
                "field_aliases": {
                    "employee_id": ["employee no", "staff id", "emp no"],
                    "national_id": ["civil id", "national id"],
                    "plan_code": ["plan", "benefit plan"],
                },
                "priority": 1,
                "is_active": True,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                "TPA Ollama configuration ready: "
                f"OCR={vision.model_name}, text={text.model_name}, endpoint={endpoint}"
            )
        )
