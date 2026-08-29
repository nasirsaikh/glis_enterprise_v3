# GLIS + Mayan EDMS integration

GLIS remains the only business application/UI. Mayan EDMS runs as a document engine and is accessed from GLIS over REST. Do not add Mayan Django apps to `INSTALLED_APPS` and do not point Mayan at the GLIS SQLite database.

## Implemented GLIS surfaces

- `/documents/` — Document Center: search, upload, download, open in Mayan.
- `/portal/tickets/<reference>/documents/` — ticket-scoped Mayan documents (HTMX partial).
- `/portal/tickets/<reference>/documents/upload/` — ticket upload with GLIS reference metadata.
- `/knowledge/<slug>/documents/` — controlled knowledge documents.
- Staff/power users can open the full Mayan UI.
- Claim, Policy and Legal categories are already offered in Document Center. When those GLIS models/screens are added, use the same metadata convention shown below.

## Environment variables

Add these to the GLIS `.env` file:

```env
MAYAN_ENABLED=True
MAYAN_BASE_URL=http://127.0.0.1:8090
MAYAN_API_TOKEN=
MAYAN_API_USERNAME=glis_service
MAYAN_API_PASSWORD=change-me
MAYAN_VERIFY_SSL=True
MAYAN_TIMEOUT=45

# IMPORTANT: create a Web/API Source in Mayan for GLIS, then put its
# current Source action execute endpoint here. Keep this configurable because
# source/action IDs are installation-specific.
MAYAN_UPLOAD_PATH=/api/v4/sources/<SOURCE_ID>/actions/<ACTION_ID>/execute/

# These can be overridden if your Mayan version exposes different routes.
MAYAN_SEARCH_PATH=/api/v4/search/search_models/documents.Document/
MAYAN_DOWNLOAD_PATH=/api/v4/documents/{document_id}/files/1/download/
MAYAN_DOCUMENT_UI_PATH=/#/documents/{document_id}/
```

For Docker, use `MAYAN_BASE_URL=http://mayan-app:8000` (or the actual Mayan service name) instead of localhost.

## Mayan configuration

1. Deploy Mayan separately (Docker is recommended).
2. Create a service account called `glis_service` or issue an API token.
3. Give that account only the document/source/search permissions GLIS requires.
4. Create a Mayan Source dedicated to GLIS API uploads.
5. Copy that Source's action execute API path into `MAYAN_UPLOAD_PATH`.
6. Create document types such as Ticket Attachment, Claim Document, Policy Document, Legal Case Document and Controlled Knowledge Document.
7. Create metadata fields corresponding to the GLIS metadata keys below.

## GLIS metadata convention

Documents uploaded from a business object should carry:

```text
glis_object_type = ticket | claim | policy | legal | knowledge
glis_object_id   = GLIS primary key
glis_reference   = human-readable GLIS reference
uploaded_by      = GLIS user email
```

Ticket uploads additionally send project, product and category. Knowledge uploads send article identity and `controlled_document=true`.

## Claims, policies and legal cases

Those applications/models are not present in this repository at the time of this integration. Do not invent duplicate business models just for EDMS. When each existing GLIS business model is introduced, add a small HTMX document panel that calls `apps.core.mayan.mayan` exactly as Tickets and Knowledge do. Search using the business reference and upload with the metadata convention above.

## Security

- GLIS performs business-object authorization before ticket document operations.
- Full Mayan UI is exposed only to GLIS staff/superusers.
- Use HTTPS and `MAYAN_VERIFY_SSL=True` in production.
- Prefer an API token/service account with least privilege.
- Do not expose Mayan database credentials to GLIS.
- Mayan should own document versions/OCR/document ACLs; GLIS should own business permissions and workflows.

## Test

After configuring Mayan:

```powershell
python manage.py check
python manage.py runserver
```

Open `/documents/`, search, upload a test PDF, and verify it appears in Mayan. Then open `/portal/tickets/<reference>/documents/` and upload a ticket document.
