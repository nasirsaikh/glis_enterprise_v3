import os
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.ai.models import AIProviderConfig


class Command(BaseCommand):
    help = "Configure a Hugging Face text provider for TPA email and member extraction."

    def add_arguments(self, parser):
        parser.add_argument(
            "--model",
            default=os.getenv("TPA_HF_MODEL", "zai-org/GLM-4.5"),
        )
        parser.add_argument(
            "--endpoint",
            default=os.getenv("TPA_HF_ENDPOINT", "https://router.huggingface.co/v1"),
        )
        parser.add_argument(
            "--secret-reference",
            default=os.getenv("TPA_HF_SECRET_REFERENCE", "HF_TOKEN"),
            help="Environment variable name containing the Hugging Face token.",
        )
        parser.add_argument(
            "--allow-sensitive-data",
            action="store_true",
            help=(
                "Allow this provider to receive sensitive TPA data. Enable only after "
                "your organization's external-data processing approval is in place."
            ),
        )
        parser.add_argument("--priority", type=int, default=50)
        parser.add_argument("--max-tokens", type=int, default=4096)

    def handle(self, *args, **options):
        model = options["model"].strip()
        endpoint = options["endpoint"].rstrip("/")
        secret_reference = options["secret_reference"].strip()

        provider, created = AIProviderConfig.objects.update_or_create(
            name="TPA Hugging Face Text Mapping",
            defaults={
                "provider": AIProviderConfig.Provider.HUGGINGFACE,
                "model_name": model,
                "endpoint": endpoint,
                "secret_reference": secret_reference,
                "temperature": Decimal("0.00"),
                "timeout_seconds": 180,
                "supports_vision": False,
                "task_capabilities": [
                    "email_extraction",
                    "member_field_mapping",
                    "structured_header_mapping",
                    "document_classification",
                ],
                "runtime_options": {"max_tokens": options["max_tokens"]},
                "allow_sensitive_data": options["allow_sensitive_data"],
                "is_active": True,
                "priority": max(0, options["priority"]),
            },
        )

        action = "created" if created else "updated"
        sensitive = "enabled" if provider.allow_sensitive_data else "disabled"
        self.stdout.write(
            self.style.SUCCESS(
                f"Hugging Face provider {action}: model={provider.model_name}, "
                f"endpoint={provider.endpoint}, sensitive-data={sensitive}, "
                f"secret={provider.secret_reference}"
            )
        )
