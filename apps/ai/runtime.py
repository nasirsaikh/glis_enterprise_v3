import base64
import json
import os
import re
import time

import httpx


def _secret(config):
    reference = (config.secret_reference or "").strip()
    return os.environ.get(reference, "") if reference else ""


def _json_from_text(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    decoder = json.JSONDecoder()
    match = re.search(r"[\[{]", text)
    if match:
        value, _ = decoder.raw_decode(text[match.start():])
        if isinstance(value, (dict, list)):
            return value
    raise ValueError("AI response did not contain a complete JSON object or array.")


def _ollama_result(response, model):
    try:
        data = response.json()
    except ValueError:
        data = {"error": response.text[:1000]}
    error = data.get("error") if isinstance(data, dict) else None
    if response.is_error or error:
        detail = str(error or response.text[:1000])
        hint = ""
        if "token repeat limit" in detail.lower():
            hint = " The OCR runner stopped repeating tokens; local OCR recovery will be used for documents. Check the Ollama/GLM-OCR version if this persists."
        raise RuntimeError(f"Ollama model '{model}' returned HTTP {response.status_code}: {detail}{hint}")
    return data


def _mock_json(user_prompt):
    def find(label, default=""):
        match = re.search(
            rf"(?im)^\s*{re.escape(label)}\s*:\s*(.+?)\s*$",
            user_prompt,
        )
        return match.group(1).strip() if match else default

    transaction = find("Transaction Type", "MEMBER_ADD").upper().replace(" ", "_")
    policy_number = find("Policy Number")
    effective_date = find("Effective Date")
    summary = find("Subject", "Mock AI email extraction")

    members = []
    blocks = re.split(r"(?im)^\s*---\s*member\s*---\s*$", user_prompt)
    for block in blocks[1:]:
        def field(label):
            match = re.search(
                rf"(?im)^\s*{re.escape(label)}\s*:\s*(.*?)\s*$",
                block,
            )
            return match.group(1).strip() if match else ""

        members.append(
            {
                "employee_id": field("Employee ID"),
                "first_name": field("First Name"),
                "middle_name": field("Middle Name"),
                "last_name": field("Last Name"),
                "date_of_birth": field("Date of Birth"),
                "gender": field("Gender"),
                "relationship": field("Relationship"),
                "principal_employee_id": field("Principal Employee ID"),
                "principal_member_id": field("Principal Member ID"),
                "national_id": field("National ID"),
                "passport_number": field("Passport Number"),
                "plan_code": field("Plan Code"),
                "effective_date": effective_date,
                "confidence": 0.99,
            }
        )

    return {
        "is_endorsement_request": True,
        "classification": transaction,
        "policy_number": policy_number,
        "transaction_type": transaction,
        "effective_date": effective_date,
        "summary": summary,
        "confidence": 0.99,
        "missing_information": [],
        "warnings": [],
        "source_references": [],
        "members": members,
    }


def _endpoint(config, default):
    return (config.endpoint or default).rstrip("/")


def generate_json(config, *, system_prompt, user_prompt, images=None, response_schema=None):
    started = time.perf_counter()
    provider = config.provider

    if provider == "mock":
        payload = _mock_json(user_prompt)
        return payload, int((time.perf_counter() - started) * 1000)

    timeout = httpx.Timeout(float(config.timeout_seconds or 120))
    secret = _secret(config)
    images = images or []
    if response_schema:
        system_prompt += "\nReturn only JSON matching this schema:\n" + json.dumps(response_schema)

    if provider == "ollama":
        endpoint = _endpoint(config, "http://127.0.0.1:11434")
        runtime_options = dict(config.runtime_options or {})
        keep_alive = runtime_options.pop("keep_alive", "15m")
        user_message = {"role": "user", "content": user_prompt}
        if images:
            user_message["images"] = [
                base64.b64encode(item["bytes"]).decode("ascii")
                for item in images
            ]
        body = {
            "model": config.model_name,
            "stream": False,
            "format": response_schema or "json",
            "messages": [
                {"role": "system", "content": system_prompt},
                user_message,
            ],
            "options": {
                "temperature": float(config.temperature or 0),
                **runtime_options,
            },
            "keep_alive": keep_alive,
        }
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{endpoint}/api/chat", json=body)

            # Ollama converts JSON schema into a llama.cpp grammar. Complex
            # schemas can be rejected by some Ollama/llama.cpp versions even
            # though the model itself is healthy. Retry in JSON mode while
            # retaining the schema instructions in the system prompt.
            schema_error = any(word in response.text.lower() for word in ("schema", "grammar", "format"))
            if response_schema and (response.status_code in {400, 422} or (response.status_code == 500 and schema_error)):
                fallback_body = {**body, "format": "json"}
                response = client.post(f"{endpoint}/api/chat", json=fallback_body)
                if response.status_code in {400, 422} and any(word in response.text.lower() for word in ("grammar", "format", "json")):
                    fallback_body.pop("format", None)
                    response = client.post(f"{endpoint}/api/chat", json=fallback_body)
            result = _ollama_result(response, config.model_name)
            raw = (result.get("message") or {}).get("content", "")
        payload = _json_from_text(raw)

    elif provider in {"openai", "openai_compatible"}:
        default = "https://api.openai.com/v1" if provider == "openai" else ""
        endpoint = _endpoint(config, default)
        if not endpoint:
            raise RuntimeError("OpenAI-compatible provider endpoint is required.")
        url = endpoint if endpoint.endswith("/chat/completions") else f"{endpoint}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["Authorization"] = f"Bearer {secret}"

        if images:
            user_content = [{"type": "text", "text": user_prompt}]
            for item in images:
                encoded = base64.b64encode(item["bytes"]).decode("ascii")
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{item['mime_type']};base64,{encoded}"
                        },
                    }
                )
        else:
            user_content = user_prompt

        body = {
            "model": config.model_name,
            "temperature": float(config.temperature or 0),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            **(config.runtime_options or {}),
        }
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
        payload = _json_from_text(raw)

    elif provider == "anthropic":
        endpoint = _endpoint(config, "https://api.anthropic.com/v1")
        headers = {
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if secret:
            headers["x-api-key"] = secret

        blocks = [{"type": "text", "text": user_prompt}]
        for item in images:
            encoded = base64.b64encode(item["bytes"]).decode("ascii")
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": item["mime_type"],
                        "data": encoded,
                    },
                }
            )
        options = config.runtime_options or {}
        body = {
            "model": config.model_name,
            "max_tokens": int(options.get("max_tokens", 4096)),
            "temperature": float(config.temperature or 0),
            "system": system_prompt,
            "messages": [{"role": "user", "content": blocks}],
        }
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{endpoint}/messages", headers=headers, json=body)
            response.raise_for_status()
            raw = "".join(
                block.get("text", "")
                for block in response.json().get("content", [])
                if block.get("type") == "text"
            )
        payload = _json_from_text(raw)

    else:
        raise RuntimeError(f"Unsupported AI provider: {provider}")

    return payload, int((time.perf_counter() - started) * 1000)


def generate_text(config, *, system_prompt, user_prompt, images=None):
    started = time.perf_counter()
    provider = config.provider
    timeout = httpx.Timeout(float(config.timeout_seconds or 120))
    secret = _secret(config)
    images = images or []

    if provider == "mock":
        return user_prompt, int((time.perf_counter() - started) * 1000)

    if provider == "ollama":
        endpoint = _endpoint(config, "http://127.0.0.1:11434")
        runtime_options = dict(config.runtime_options or {})
        keep_alive = runtime_options.pop("keep_alive", 0 if images else "15m")
        api = runtime_options.pop("ollama_api", "chat")
        options = {
            "temperature": float(config.temperature or 0),
            **runtime_options,
        }
        user_message = {"role": "user", "content": user_prompt}
        if images:
            user_message["images"] = [base64.b64encode(item["bytes"]).decode("ascii") for item in images]
            options.setdefault("num_predict", 4096)
        body = {
            "model": config.model_name, "stream": False,
            "messages": [
                *([{"role": "system", "content": system_prompt}] if system_prompt else []),
                user_message,
            ],
            "options": options, "keep_alive": keep_alive,
        }
        generate_body = {
            "model": config.model_name, "stream": False, "prompt": user_prompt,
            "options": options, "keep_alive": keep_alive,
            **({"system": system_prompt} if system_prompt else {}),
            **({"images": user_message["images"]} if images else {}),
        }
        with httpx.Client(timeout=timeout) as client:
            url = f"{endpoint}/api/generate" if api == "generate" else f"{endpoint}/api/chat"
            response = client.post(url, json=generate_body if api == "generate" else body)
            if api != "generate" and response.status_code in {404, 405} and "model" not in response.text.lower():
                response = client.post(f"{endpoint}/api/generate", json=generate_body)
            result = _ollama_result(response, config.model_name)
            raw = (result.get("message") or {}).get("content") or result.get("response", "")

    elif provider in {"openai", "openai_compatible"}:
        default = "https://api.openai.com/v1" if provider == "openai" else ""
        endpoint = _endpoint(config, default)
        if not endpoint:
            raise RuntimeError("OpenAI-compatible provider endpoint is required.")
        url = endpoint if endpoint.endswith("/chat/completions") else f"{endpoint}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        content = user_prompt
        if images:
            content = [{"type": "text", "text": user_prompt}]
            for item in images:
                encoded = base64.b64encode(item["bytes"]).decode("ascii")
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{item['mime_type']};base64,{encoded}"},
                    }
                )
        body = {
            "model": config.model_name,
            "temperature": float(config.temperature or 0),
            "messages": [
                *([{"role": "system", "content": system_prompt}] if system_prompt else []),
                {"role": "user", "content": content},
            ],
            **(config.runtime_options or {}),
        }
        body.pop("keep_alive", None)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]

    elif provider == "anthropic":
        endpoint = _endpoint(config, "https://api.anthropic.com/v1")
        headers = {
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        if secret:
            headers["x-api-key"] = secret
        blocks = [{"type": "text", "text": user_prompt}]
        for item in images:
            encoded = base64.b64encode(item["bytes"]).decode("ascii")
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": item["mime_type"],
                        "data": encoded,
                    },
                }
            )
        options = config.runtime_options or {}
        body = {
            "model": config.model_name,
            "max_tokens": int(options.get("max_tokens", 4096)),
            "temperature": float(config.temperature or 0),
            "system": system_prompt or "",
            "messages": [{"role": "user", "content": blocks}],
        }
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{endpoint}/messages", headers=headers, json=body)
            response.raise_for_status()
            raw = "".join(
                block.get("text", "")
                for block in response.json().get("content", [])
                if block.get("type") == "text"
            )
    else:
        raise RuntimeError(f"Unsupported AI provider: {provider}")

    return (raw or "").strip(), int((time.perf_counter() - started) * 1000)
