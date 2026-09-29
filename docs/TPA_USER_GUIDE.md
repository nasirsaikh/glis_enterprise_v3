# GLIS TPA Member Management — SmartEndorse-style User Guide

## Operating model

The GLIS TPA module follows the SmartEndorse operating pattern while keeping GLIS tickets, SLA, approvals, notifications and audit infrastructure underneath the workflow.

Flow:

Intake & Correction → Validation → Approval → TPA Processing / Query → Complete

AI is limited to extraction and semantic mapping. Policy/member eligibility, plan validation, dependent-principal rules, premium/refund calculation, STP, approval and final member updates are deterministic GLIS logic.

## Initial Policy Enrollment

A brand-new policy is created from:

Portal → TPA Operations → Initial Policy Enrollment

This is intentionally separate from endorsements. Initial setup creates a Draft policy for an Individual or Corporate Sponsor together with the Insurance Company, optional TPA route, policy dates, currency/STP/backdating settings, first Benefit Plan, PolicyAccess for the setup user, and a dedicated NEW_POLICY_ENROLLMENT transaction.

Additional plans and the complete opening census are added inside that case. The opening census can be entered manually or loaded through the same Excel/CSV/PDF/image OCR intake used later for endorsements.

After validation, approval/STP and TPA processing complete successfully, GLIS activates the policy and records initial_enrollment_completed_at and initial_enrollment_completed_by. Only then is the policy available for New Endorsement, except legacy active policies that already have active member enrollments.

## Endorsements

Portal → TPA Member Management → New Endorsement

The endorsement form no longer includes New Policy Enrollment. It supports:

- Member Addition
- Member Termination
- Member Deletion / Void
- Policy Cancellation

For spouse, child or other dependent additions, a parent Principal is mandatory. Manual entry provides a policy-aware Principal selector. File/OCR intake can use principal_employee_id or principal_member_id.

## File upload and AI OCR

The transaction page contains one Source Documents & AI OCR intake zone. Up to 20 related files can be supplied together so ID front/back, passport pages and supporting evidence can be treated as one evidence bundle.

| Source | Processing |
|---|---|
| CSV | deterministic structured parsing |
| XLSX | deterministic structured parsing |
| XLS | deterministic structured parsing with xlrd |
| text PDF | pypdf text extraction, then text-model mapping |
| scanned PDF | PyMuPDF page rendering → vision OCR → text-model mapping |
| PNG/JPG/JPEG/WEBP | vision OCR → text-model mapping |

The default operational AI configuration uses two local Ollama providers:

1. **TPA Ollama Vision OCR** using `glm-ocr`:
   - endpoint `http://127.0.0.1:11434`
   - `supports_vision=True`
   - `allow_sensitive_data=True`
   - capability `document_extraction`
   - 600 second timeout for scanned PDFs / image batches
2. **TPA Ollama Text Mapping** using `qwen2.5:7b`:
   - endpoint `http://127.0.0.1:11434`
   - `supports_vision=False`
   - `allow_sensitive_data=True`
   - capability `member_field_mapping`
   - capability `email_extraction`
   - capability `structured_header_mapping`

Keep OCR and JSON mapping separate. The vision model transcribes document evidence; the text model converts OCR/email evidence into strict canonical member JSON. Business decisions remain outside the LLM.

The mapper uses the MEMBER_FIELD_MAPPING extraction profile and its training examples. AI interaction metadata and SourceDocument processing results remain auditable.

### Intake correction

Submitted/OCR values are preserved. Use the pencil action to edit working values. Save & Revalidate writes corrected_data, records before/after values in TransactionEvent and immediately reruns deterministic validation.

## Validation, pricing and STP

Validation includes policy period/backdating, mandatory fields, plan validity, duplicate identifiers, active-member lookup for termination/deletion and dependent/principal rules.

Premium/refund amounts are calculated with deterministic Decimal arithmetic from Benefit Plan configuration.

If validation is clean and STP rules pass, the case auto-approves and dispatches to TPA. Otherwise it follows the GLIS approval workflow or manual approval authority.

Approval means dispatch to TPA; it no longer immediately changes member records.

## TPA processing

TPA workflow statuses include:

- sent_to_tpa
- tpa_in_progress
- tpa_query
- completed

A permitted TPA processor starts the case, then records card/member number, TPA effective date and TPA premium/refund amount per row.

For additions and initial enrollment, card/member number is required before completion. TPA effective date and TPA amount are required for applicable member rows.

Complete TPA Processing persists the TPA-final card/member number, effective date and final premium/refund amount into the permanent enrollment where applicable, performs the deterministic member/enrollment update and marks the case completed. Initial Policy Enrollment completion also activates the policy.

## TPA query and embedded chat

If TPA needs more information, Raise Query to Requester creates a dedicated GLIS query Ticket related to the main transaction Ticket and pauses the case in TPA Query.

GLIS still stores normal TicketComment and TicketAttachment records for SLA/audit/notifications, but requester and TPA communication is rendered as DaisyUI chat directly inside the TPA Processing step. Users do not have to navigate to the ticket page.

Resolving the query closes the query ticket and resumes TPA processing. Resolved conversation history remains visible inside the case.

## Email intake

Email endorsements use the same downstream workflow as portal uploads. Email-body AI can identify policy, endorsement type, effective date and member data. Email attachments enter the same SourceDocument processor used by portal uploads, including Excel, PDF and image OCR.

Email intake is for endorsements only. If AI classifies a message as New Policy Enrollment, GLIS sends it to review and instructs the user to use Initial Policy Enrollment.

Manual/provider testing is available at:

/portal/tpa/inbound-emails/

### Automatic IMAP reading

Configure:

TPA_IMAP_HOST=mail.example.com
TPA_IMAP_PORT=993
TPA_IMAP_USERNAME=tpa@example.com
TPA_IMAP_PASSWORD=<secret>
TPA_IMAP_FOLDER=INBOX
TPA_IMAP_USE_SSL=1

Run manually:

python manage.py process_tpa_mailbox --username YOUR_USERNAME

Store unread messages without AI:

python manage.py process_tpa_mailbox --username YOUR_USERNAME --no-ai

The same handler is registered in GLIS Job Center as:

tpa.poll_inbound_mailbox

It searches unread mail, deduplicates using Message-ID/IMAP UID, stores body/attachments, processes the endorsement through AI/OCR and marks the IMAP message as seen.

## Permissions

| Permission | Purpose |
|---|---|
| tpa.create_enrollment | create Initial Policy Enrollment |
| tpa.create_endorsement | create post-enrollment endorsements |
| tpa.approve_endorsement | manual approval authority |
| tpa.process_endorsement | TPA processing/query/completion |
| tpa.configure_tpa | administrative TPA access |

PolicyAccess additionally controls policy-scoped view/create/approve/process authority.

## Local Ollama setup

Install/pull the local TPA models before processing scanned documents or live email intake:

```bash
ollama pull glm-ocr
ollama pull qwen2.5:7b
ollama serve
```

Then create/update only the TPA Ollama provider/profile configuration (no demo business data):

```bash
python manage.py configure_tpa_ollama
# Optional exact local model tags:
python manage.py configure_tpa_ollama --ocr-model glm-ocr:q8_0 --text-model qwen2.5:7b
```

The seed command creates the provider records in Django Admin. If your installed OCR model tag is different (for example a quantized tag), update **TPA Ollama Vision OCR → Model name** to the exact Ollama model tag installed on the server.

## AI provider configuration

AIProviderConfig supports Mock, Ollama, OpenAI-compatible/OpenAI and Anthropic runtimes.

For member documents, set allow_sensitive_data=True only on providers approved for that data.

secret_reference stores the environment-variable name, not the actual secret. For example, secret_reference may be OPENAI_API_KEY while the actual value lives in the runtime environment.

## Sample data

After migrations:

python manage.py seed_tpa_sample --username YOUR_USERNAME

The idempotent seed creates/updates:

- Demo Corporate sponsor
- Demo Insurance Company
- NextCare Demo TPA
- endorsement-enabled DEMO-MED-<year> policy
- GOLD and SILVER plans
- existing Principal/Spouse/Child family
- PolicyAccess and TPA Demo Operators permissions
- TPA Ollama Vision OCR (`glm-ocr`) as the primary document OCR provider
- TPA Ollama Text Mapping (`qwen2.5:7b`) as the primary member/email mapping provider
- low-priority Mock AI only for deterministic offline sample-email processing and automated tests
- email/document/member mapping profiles
- valid and invalid sample inbound emails

## Deployment / test sequence

git pull origin main
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py makemigrations --check
python manage.py test apps.tpa
python manage.py seed_tpa_sample --username YOUR_USERNAME
python manage.py runserver

Primary routes:

/portal/tpa/
/portal/tpa/policy-enrollment/
/portal/tpa/transactions/
/portal/tpa/inbound-emails/
/portal/tpa/guide/
