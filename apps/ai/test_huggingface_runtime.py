import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.ai.runtime import generate_json, generate_text


class HuggingFaceRuntimeTests(SimpleTestCase):
    def _config(self, **overrides):
        values = {
            "provider": "huggingface",
            "model_name": "zai-org/GLM-4.5",
            "endpoint": "",
            "secret_reference": "HF_TOKEN",
            "temperature": 0,
            "timeout_seconds": 120,
            "runtime_options": {"max_tokens": 1200},
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    @patch.dict(os.environ, {"HF_TOKEN": "hf_test_token"}, clear=False)
    @patch("apps.ai.runtime.httpx.Client")
    def test_generate_json_uses_huggingface_router_and_bearer_token(self, client_cls):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"policy_number":"P/230/1010/2025/15428","members":[]}'
                    }
                }
            ]
        }
        client = client_cls.return_value.__enter__.return_value
        client.post.return_value = response

        payload, duration_ms = generate_json(
            self._config(),
            system_prompt="Return JSON only.",
            user_prompt="Extract the policy number.",
            response_schema={"type": "object"},
        )

        self.assertEqual(payload["policy_number"], "P/230/1010/2025/15428")
        self.assertGreaterEqual(duration_ms, 0)
        url = client.post.call_args.args[0]
        kwargs = client.post.call_args.kwargs
        self.assertEqual(url, "https://router.huggingface.co/v1/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer hf_test_token")
        self.assertEqual(kwargs["json"]["model"], "zai-org/GLM-4.5")
        self.assertEqual(kwargs["json"]["max_tokens"], 1200)
        self.assertNotIn("response_format", kwargs["json"])

    @patch.dict(os.environ, {"HF_TOKEN": "hf_test_token"}, clear=False)
    @patch("apps.ai.runtime.httpx.Client")
    def test_generate_text_supports_custom_huggingface_endpoint(self, client_cls):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": "MEMBER_ADD"}}]
        }
        client = client_cls.return_value.__enter__.return_value
        client.post.return_value = response

        text, _ = generate_text(
            self._config(endpoint="https://example.hf.test/v1"),
            system_prompt="Classify the request.",
            user_prompt="Please add this member.",
        )

        self.assertEqual(text, "MEMBER_ADD")
        self.assertEqual(
            client.post.call_args.args[0],
            "https://example.hf.test/v1/chat/completions",
        )
