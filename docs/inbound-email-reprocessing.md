# Inbound email reprocessing and OCR recovery

In Django admin, open **TPA → Inbound emails**. Select messages and choose
**Reprocess selected emails**, or open one message and click **Save and reprocess**.
The latter saves edited body text, processing hints, and attachments before retrying.

Retries use the existing Job Center queue and scheduler. Keep
`JOB_CENTER_ENABLED=1` and restart the app after pulling the update. Refresh the
email list to check **Processing state**, **Processing stage**, and **Processing
error**. The queued job's result/error is also available in Job Center admin.

The retry rechecks sender authority and organization access, rereads the email
body and all attachments, and updates the linked intake endorsement. Existing
member corrections and source files are preserved. Duplicate queue clicks are
blocked. Endorsements that have left intake cannot be reprocessed.

## Configure the two model roles

- OCR provider: a vision model such as `glm-ocr`, with **Supports vision** and
  **Allow sensitive data** enabled, and `document_extraction` capability.
- Mapping/email provider: a text model such as `qwen2.5:7b`, with **Supports
  vision** disabled and **Allow sensitive data** enabled. Add `email_extraction`
  and `member_field_mapping` capabilities.

GLM-OCR transcribes images; the text model maps that transcription into the
Pydantic member schema. The OCR request uses the model's `Text Recognition:`
prompt. Ollama schema/grammar errors retry with JSON mode while application
validation remains active. Ollama's actual error message is retained for review.

After pulling, install `requirements.txt`. Scanned PDFs/images recover through
local Docling OCR when vision extraction fails or recoverable fields are missing.
Docling/EasyOCR may need their model assets downloaded on first use. An optional
installed Tesseract executable is used if Docling fails; set
`TPA_TESSERACT_CMD` if it is not on PATH. All document recovery runs locally.

Canonical CSV/Excel rows and member tables in email HTML are read directly,
preserving leading zeros and empty cells. Manual evidence upload supports EML
and Outlook MSG containers, including their CSV/Excel/PDF/image attachments.
Unknown benefit plans, relationships, or other facts are left for correction
when the evidence does not contain them.
