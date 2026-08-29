import json
import logging
import os
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)


class MayanError(RuntimeError):
    pass


def _env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


class MayanClient:
    """Mayan EDMS gateway used by GLIS views.

    Configuration is environment driven so Mayan stays external while every
    business screen remains inside the existing GLIS Django project.
    """

    def __init__(self):
        self.base_url = os.getenv("MAYAN_BASE_URL", "http://127.0.0.1:8090").rstrip("/") + "/"
        self.timeout = int(os.getenv("MAYAN_TIMEOUT", "45"))
        self.verify_ssl = _env_bool("MAYAN_VERIFY_SSL", True)
        self.enabled = _env_bool("MAYAN_ENABLED", False)
        self.upload_path = os.getenv("MAYAN_UPLOAD_PATH", "")
        self.search_path = os.getenv("MAYAN_SEARCH_PATH", "/api/v4/search/search_models/documents.Document/")
        self.download_path = os.getenv("MAYAN_DOWNLOAD_PATH", "/api/v4/documents/{document_id}/files/1/download/")
        self.document_ui_path = os.getenv("MAYAN_DOCUMENT_UI_PATH", "/#/documents/{document_id}/")
        self.session = requests.Session()
        token = os.getenv("MAYAN_API_TOKEN", "").strip()
        username = os.getenv("MAYAN_API_USERNAME", "").strip()
        password = os.getenv("MAYAN_API_PASSWORD", "")
        if token:
            self.session.headers.update({"Authorization": f"Token {token}"})
        elif username:
            self.session.auth = (username, password)
        self.session.headers.update({"Accept": "application/json"})

    def _url(self, path):
        return urljoin(self.base_url, path.lstrip("/"))

    def _request(self, method, path, **kwargs):
        if not self.enabled:
            raise MayanError("Mayan EDMS integration is disabled. Set MAYAN_ENABLED=True.")
        try:
            response = self.session.request(method, self._url(path), timeout=self.timeout, verify=self.verify_ssl, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            logger.exception("Mayan EDMS request failed: %s %s", method, path)
            raise MayanError(str(exc)) from exc

    def health(self):
        try:
            response = self._request("GET", "/api/v4/")
            return {"ok": True, "status_code": response.status_code}
        except MayanError as exc:
            return {"ok": False, "error": str(exc)}

    def get_document(self, document_id):
        return self._request("GET", f"/api/v4/documents/{document_id}/").json()

    def search_documents(self, query="", page=1, page_size=25):
        params = {"page": page, "page_size": page_size}
        if query:
            params["q"] = query
        return self._request("GET", self.search_path, params=params).json()

    def upload_document(self, uploaded_file, *, label="", metadata=None):
        if not self.upload_path:
            raise MayanError("MAYAN_UPLOAD_PATH is not configured with the GLIS Source action execute endpoint.")
        uploaded_file.seek(0)
        files = {"file": (uploaded_file.name, uploaded_file, getattr(uploaded_file, "content_type", "application/octet-stream"))}
        data = {"label": label or uploaded_file.name}
        if metadata:
            data["metadata"] = json.dumps(metadata)
        response = self._request("POST", self.upload_path, files=files, data=data)
        payload = response.json() if response.content else {}
        document_id = payload.get("id") or payload.get("document_id")
        if not document_id and isinstance(payload.get("document"), dict):
            document_id = payload["document"].get("id")
        return payload, document_id

    def download_document(self, document_id):
        return self._request("GET", self.download_path.format(document_id=document_id), stream=True)

    def delete_document(self, document_id):
        return self._request("DELETE", f"/api/v4/documents/{document_id}/")

    def document_url(self, document_id):
        return self._url(self.document_ui_path.format(document_id=document_id))

    @property
    def admin_url(self):
        return self.base_url


mayan = MayanClient()
