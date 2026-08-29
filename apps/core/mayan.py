import logging
from urllib.parse import urljoin

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class MayanError(RuntimeError):
    pass


class MayanClient:
    """Small, isolated client for the Mayan EDMS REST API.

    GLIS remains the user-facing application. Endpoint paths are configurable so
    Mayan upgrades do not require business-view changes.
    """

    def __init__(self):
        self.base_url = settings.MAYAN_BASE_URL.rstrip("/") + "/"
        self.timeout = settings.MAYAN_TIMEOUT
        self.verify_ssl = settings.MAYAN_VERIFY_SSL
        self.session = requests.Session()
        token = settings.MAYAN_API_TOKEN.strip()
        if token:
            self.session.headers.update({"Authorization": f"Token {token}"})
        elif settings.MAYAN_API_USERNAME:
            self.session.auth = (settings.MAYAN_API_USERNAME, settings.MAYAN_API_PASSWORD)
        self.session.headers.update({"Accept": "application/json"})

    @property
    def enabled(self):
        return bool(settings.MAYAN_ENABLED and self.base_url.strip("/"))

    def _url(self, path):
        return urljoin(self.base_url, path.lstrip("/"))

    def _request(self, method, path, **kwargs):
        if not self.enabled:
            raise MayanError("Mayan EDMS integration is not enabled.")
        try:
            response = self.session.request(method, self._url(path), timeout=self.timeout, verify=self.verify_ssl, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            logger.exception("Mayan EDMS request failed: %s %s", method, path)
            raise MayanError(str(exc)) from exc

    def health(self):
        try:
            response = self._request("GET", settings.MAYAN_HEALTH_PATH)
            return {"ok": True, "status_code": response.status_code}
        except MayanError as exc:
            return {"ok": False, "error": str(exc)}

    def get_document(self, document_id):
        return self._request("GET", f"/api/v4/documents/{document_id}/").json()

    def search_documents(self, query="", page=1, page_size=25):
        params = {"page": page, "page_size": page_size}
        if query:
            params["q"] = query
        response = self._request("GET", settings.MAYAN_SEARCH_PATH, params=params)
        return response.json()

    def upload_document(self, uploaded_file, *, label="", metadata=None):
        """Upload through the configured Mayan Source action execute endpoint.

        Set MAYAN_UPLOAD_PATH to the Source action execute URL for the Mayan
        source created for GLIS. This avoids hard-coding a source/action ID.
        """
        if not settings.MAYAN_UPLOAD_PATH:
            raise MayanError("MAYAN_UPLOAD_PATH is not configured.")
        uploaded_file.seek(0)
        files = {"file": (uploaded_file.name, uploaded_file, getattr(uploaded_file, "content_type", "application/octet-stream"))}
        data = {"label": label or uploaded_file.name}
        if metadata:
            import json
            data["metadata"] = json.dumps(metadata)
        response = self._request("POST", settings.MAYAN_UPLOAD_PATH, files=files, data=data)
        payload = response.json() if response.content else {}
        document_id = payload.get("id") or payload.get("document_id")
        if not document_id and isinstance(payload.get("document"), dict):
            document_id = payload["document"].get("id")
        return payload, document_id

    def download_document(self, document_id):
        path = settings.MAYAN_DOWNLOAD_PATH.format(document_id=document_id)
        return self._request("GET", path, stream=True)

    def delete_document(self, document_id):
        return self._request("DELETE", f"/api/v4/documents/{document_id}/")

    def document_url(self, document_id):
        template = settings.MAYAN_DOCUMENT_UI_PATH
        return self._url(template.format(document_id=document_id))


mayan = MayanClient()
