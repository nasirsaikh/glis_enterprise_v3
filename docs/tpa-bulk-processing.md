# Bulk cards and processing details

Open an endorsement's **TPA Processing** step and start processing. The member
list has search, readiness filters, and 20 rows per page. **Notes** opens a modal
for the amount override reason and processing description. **Save member and
notes** saves those notes with the row's card, date, and amount.

For large lists:

1. Choose **Download members (Excel)**. This downloads every member in the
   endorsement, including members on other pages. CSV is also available.
2. Fill the green columns: `card_number`, `effective_date`, `amount`,
   `override_reason`, and `comments`. Excel identifiers are text, so leading
   zeros stay intact. Keep `transaction_reference`, `action_id`, `employee_id`,
   `member_name`, and `row_version` unchanged. You may sort or remove rows to
   upload a subset. Match returned TPA card numbers against `action_id` or the
   employee identifier; keep the original action ID with that member.
3. Choose **Upload card details → Preview changes**. The preview shows update,
   skipped, and error counts. Download the full error report when necessary.
   No data is changed during preview. Empty card rows for additions are skipped;
   blank notes preserve existing notes. Dates must be valid, and amount changes
   require an override reason. Duplicate cards and other endorsements' member
   IDs are rejected.
4. Choose **Apply validated batch**. All validated rows save together, with
   per-member audit events and a batch summary. Any error or member change since
   preview blocks the entire batch. Download a fresh list when a row is stale.
5. Once all members show **Ready**, complete TPA processing. Export/import does
   not approve an endorsement, issue member records, or complete the workflow.

Each upload supports up to **10,000 rows / 10 MB**. Preview tokens expire after
30 minutes and are bound to the processing user and endorsement. Exports,
previews, error reports, and updates require organization-scoped TPA processing
authority. Existing-member endorsements retain their existing cards.

## Local OCR when GLM-OCR fails

An Ollama `prediction aborted, token repeat limit reached` error is a runner
failure. The app now recovers text before trying member mapping, instead of
asking the mapper to process an empty OCR result. Recovery attempts and recovered
text are recorded in the source document's extraction history/JSON.

To bypass a persistently failing vision runner, set this in `.env` and restart:

```dotenv
TPA_OCR_ENGINE=local
TPA_DOCLING_FALLBACK_ENABLED=1
```

Local mode reads embedded PDF text or uses Docling OCR. If Docling's layout
models fail, direct EasyOCR handles English/Arabic and rotated pages; installed
Tesseract is the last fallback. The text provider still uses Ollama for Pydantic
member mapping. Install `requirements.txt`; Docling/EasyOCR download their local
model assets on first use. All-backend failures display the actual error from
each recovery engine.

Email intake preserves HTML paragraph/table boundaries. Explicit, unambiguous
policy/type headers can repair a member-only AI response, and relative effective
dates use the email's received date in the configured timezone. Original AI
output and the classification source stay available for review. Sender authority,
policy scope, and normal member validation remain mandatory; ambiguous or
contradictory requests require review.
