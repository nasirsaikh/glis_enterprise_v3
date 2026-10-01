# GLIS TPA Member Management — Automated Endorsement Operations Guide

## 1. Operating model

The GLIS TPA module is an automated endorsement-processing platform built inside the existing GLIS portal. It reuses GLIS authentication, policy access, tickets, approvals, SLA/TAT, notifications, attachments, audit events, HTMX, Job Center, Bootstrap 5.3.2.

Normal automated flow:

~~~text
Office 365 Inbox
→ Microsoft Graph delta sync
→ email classification
→ sender authority validation
→ policy resolution
→ body + attachment extraction
→ Intake & Correction
→ deterministic validation
→ STP / Approval
→ TPA Processing
→ Query/Discussion where required
→ Card Dispatch when required
→ Complete
→ Permanent member/policy update
~~~

AI is assistive. It may classify/extract/map evidence, but it does not decide sender authority, eligibility, duplicate-member rules, premium/refund, backdating, STP, approval or final validation.

---

## 2. Supported endorsement types

The TPA transaction model distinguishes:

- New Policy Enrollment — dedicated setup workflow only;
- Member Addition;
- Member Deletion / Void;
- Member Termination — permanent;
- Temporary Suspension;
- Member Reactivation;
- Policy Cancellation.

Temporary suspension is not permanent termination. Reactivation is available only for eligible suspended enrollments.

Manual suspension captures a required suspension reason and an optional expected reactivation date. Email extraction maps `temporary_until` into the same structured transaction field, so both intake channels use the same completion logic.

---

## 3. Initial Policy Enrollment

Create a new policy from:

~~~text
Portal → TPA Operations → Initial Policy Enrollment
~~~

Initial setup creates a Draft policy and a dedicated New Policy Enrollment transaction. Configure the global organization, insurer, processing organizations, dates, currency, STP/backdating, physical-card requirement and benefit plans.

The opening census can be entered manually or loaded through the same structured/OCR evidence pipeline used by later endorsements.

Permanent enrollment records are applied only after final TPA completion.

---

## 4. Office 365 / Microsoft Graph

### 4.1 Primary integration

Microsoft Graph v1.0 with OAuth2 client credentials is the primary automated mailbox transport. No interactive Microsoft login is required for each synchronization.

Recommended Microsoft Graph application permission:

~~~text
Mail.Read (Application)
~~~

Use Mail.ReadWrite only if GLIS is later configured to modify/move/categorize messages in Microsoft 365.

### 4.2 Azure / Entra setup

1. Create an App Registration in Microsoft Entra ID.
2. Record Tenant ID and Client ID.
3. Add Microsoft Graph Application permission Mail.Read.
4. Grant tenant administrator consent.
5. Create a client secret or use the organization's approved credential store.
6. Apply Exchange/Entra application-access restrictions if only a specific shared mailbox should be readable.
7. Configure GLIS environment variables.
8. Restart the Django application so Job Center loads the configuration.

Never put the client secret in Django Admin, source control, logs or editable JSON.

### 4.3 Environment configuration

~~~dotenv
TPA_MAIL_PROVIDER=office365_graph
TPA_MAIL_ENABLED=True
TPA_MAIL_AUTO_PROCESS_AI=True
TPA_MAIL_MAX_MESSAGES_PER_RUN=50
TPA_MAIL_SYNC_CRON=*/5 * * * *
TPA_MAIL_ACTOR_USERNAME=tpa-service-user
TPA_EMAIL_CLASSIFICATION_MIN_CONFIDENCE=0.75

TPA_O365_TENANT_ID=00000000-0000-0000-0000-000000000000
TPA_O365_CLIENT_ID=00000000-0000-0000-0000-000000000000
TPA_O365_CLIENT_SECRET=use-a-secret-manager
TPA_O365_MAILBOX=endorsements@example.com
TPA_O365_FOLDER=Inbox
TPA_O365_RECEIVED_AFTER=
TPA_O365_TIMEOUT_SECONDS=60
~~~

<code>TPA_MAIL_SYNC_CRON</code> controls the effective Job Center schedule. The default <code>*/5 * * * *</code> runs every five minutes.

<code>TPA_MAIL_ACTOR_USERNAME</code> identifies the GLIS service user used for automated audit records. If it is absent, the registered Job Center handler falls back to an active superuser.

### 4.4 Automatic synchronization

The seeded Job Center job is:

~~~text
TPA Office365 Mailbox Sync
handler: tpa.poll_inbound_mailbox
~~~

The scheduler starts with Django. No Celery worker/beat and no separate mailbox command are required.

Graph synchronization:

- obtains an application token;
- uses Inbox message delta synchronization;
- persists the delta link in <code>TPAMailboxSyncState</code>;
- stores new messages and attachments;
- classifies/processes qualifying mail;
- persists review/failure states;
- retries transient Graph 429/5xx requests;
- remains idempotent after application restarts.

Deduplication uses provider message ID, mailbox + internetMessageId and attachment SHA-256 hashes.

### 4.5 Manual diagnostics

Normal operation does not require these commands, but they remain useful for recovery/testing:

~~~bash
python manage.py process_tpa_mailbox --username YOUR_USERNAME
python manage.py process_tpa_mailbox --username YOUR_USERNAME --no-ai
~~~

Legacy IMAP remains an explicit fallback only when <code>TPA_MAIL_PROVIDER=imap</code>.

---

## 5. Inbound Email monitor

Open:

~~~text
/portal/tpa/inbound-emails/
~~~

This page is an operational monitor, not primarily an upload page.

It displays:

- Graph connection/configuration;
- mailbox and folder;
- effective schedule;
- next run / last job state;
- last attempted and successful sync;
- last error;
- processed count;
- review count;
- ignored/non-endorsement count;
- failed count;
- scheduler enabled/disabled.

Authorized staff can use **Sync Inbox Now**.

**Manual Intake / Reprocess** remains available only for fallback, recovery, testing or a manually sourced request.

---

## 6. Email evidence and audit

For Graph messages GLIS retains, where supplied:

- Graph message ID;
- internetMessageId;
- conversation ID;
- mailbox;
- sender name/address;
- To/CC;
- subject;
- received date/time;
- text body;
- sanitized HTML body;
- attachment metadata;
- original attachments;
- source hashes;
- AI extraction result;
- raw normalized AI output;
- classification and confidence;
- processing stage/state/error;
- linked transaction;
- timestamps.

Original evidence is not replaced by corrected operational data.

The inbound-email audit also stores the AI provider and model name used for extraction. Failed/review-required manually uploaded evidence can be deleted by an authorized intake editor; Office365/email-linked evidence is immutable and remains available for reprocessing/audit.

---

## 7. Classification

The email extraction model first decides whether a message is relevant to endorsement processing.

Canonical classifications include:

- MEMBER_ADD
- MEMBER_DELETE
- MEMBER_TERMINATE
- MEMBER_SUSPEND
- MEMBER_REACTIVATE
- POLICY_CANCEL
- QUERY_REPLY
- NOT_ENDORSEMENT
- NEEDS_REVIEW

Clearly unrelated mail is retained as configured but marked Ignored and does not create a MemberTransaction.

Low-confidence/uncertain mail is routed to Needs Review rather than guessed.

The default classification confidence threshold is controlled by:

~~~dotenv
TPA_EMAIL_CLASSIFICATION_MIN_CONFIDENCE=0.75
~~~

---

## 8. Strict AI extraction contract

The extraction profile requires JSON conceptually shaped as:

~~~json
{
  "is_endorsement_request": true,
  "classification": "MEMBER_ADD",
  "confidence": 0.97,
  "policy_number": "MED-123",
  "transaction_type": "MEMBER_ADD",
  "transaction_reference": null,
  "effective_date": "2026-10-01",
  "refund_basis": null,
  "temporary_until": null,
  "remarks": "",
  "summary": "",
  "members": [],
  "missing_information": [],
  "warnings": [],
  "source_references": []
}
~~~

Free-form model output does not directly mutate production membership.

---

## 9. AI provider configuration

AIProviderConfig supports Mock, Ollama, OpenAI-compatible/OpenAI and Anthropic runtimes.

A provider processing member identity/medical evidence must explicitly allow sensitive data.

### Local Ollama pattern

Recommended separation:

1. Vision/document OCR provider
   - model: GLM-OCR or approved equivalent;
   - supports_vision=True;
   - capability: document_extraction;
   - allow_sensitive_data=True only when approved.

2. Text mapping provider
   - model: qwen2.5:7b or approved equivalent;
   - supports_vision=False;
   - capabilities:
     - member_field_mapping
     - email_extraction
     - structured_header_mapping.

Install:

~~~bash
ollama pull glm-ocr
ollama pull qwen2.5:7b
ollama serve
~~~

Configure provider/profile records:

~~~bash
python manage.py configure_tpa_ollama
python manage.py configure_tpa_ollama --ocr-model glm-ocr:q8_0 --text-model qwen2.5:7b
~~~

Django Admin can manage extraction profiles, prompts/instructions, aliases and training examples.

---

## 10. Sender authority

AI never authorizes a sender.

Configure <code>TPAEmailAuthority</code> for:

- email address;
- optional linked user;
- global organization;
- optional specific policy;
- permitted transaction types;
- valid-from / valid-until;
- active flag.

If a Graph sender is not authorized for the resolved policy and endorsement type, GLIS retains the evidence, marks it Unauthorized Sender, records the reason and notifies eligible review staff.

Manual/test intake can proceed only when the operator already has server-side TPA/policy authority.

---

## 11. Policy identification

AI may extract the policy number, but Django resolves it against the database.

Automatic processing proceeds only when a valid active policy can be deterministically resolved and the sender is authorized for that policy.

Missing, ambiguous, inactive or unauthorized policy evidence goes to review.

---

## 12. Evidence processing

All evidence belongs to one logical transaction source bundle.

| Source | Processing |
|---|---|
| CSV | deterministic parser |
| XLSX | deterministic parser with openpyxl |
| XLS | deterministic parser with xlrd |
| Text PDF | native text extraction first |
| Scanned PDF | PyMuPDF page rendering → vision OCR |
| PNG/JPG/JPEG/WebP | vision OCR |
| EML | email/body/attachment pipeline |
| Manual entry | canonical Django form |

OCR output is mapped by the configured text model into canonical member JSON.

New sources append/merge through deterministic matching and provenance. Conflicts generate warnings rather than silently overwriting corrected values.

Failed OCR remains recoverable: files are retained, state moves to review, exact errors/provider/model are recorded, and authorized users can reprocess later.

---

## 13. Intake & Correction

The transaction detail page is the central workspace.

It supports:

- Add / Reprocess Evidence;
- source status/error listing;
- protected source download;
- authorized raw extraction JSON modal;
- Reprocess Evidence;
- existing-member selection;
- bulk pasted card numbers;
- Add Member Manually modal;
- Validated and Errors / Needs Correction tabs;
- row correction/removal while intake remains editable.

Manual member entry uses HTMX. Invalid/duplicate data is returned into the modal without creating a MemberAction or unnecessarily closing the dialog.

Manual addition duplicate checks cover active policy enrollments and pending rows using employee number, Civil/National ID and passport number.

---

## 14. Multiple members and provenance

One transaction may contain 1, 10, 100 or more MemberAction rows.

Row provenance can identify evidence such as:

- email body;
- attachment;
- OCR;
- structured import;
- policy selection;
- manual user;
- correction.

Source conflicts are stored as warnings.

---

## 15. Existing-member selection and pasted cards

For deletion, termination and suspension, active policy enrollments are available for selection.

For reactivation, suspended enrollments are available.

The bulk card parser accepts line breaks, comma, semicolon and whitespace and reports:

- matched;
- not found;
- duplicate input;
- inactive/ineligible cards.

Only eligible matched enrollments are added.

Policy Cancellation automatically populates all active enrollments; the user does not manually select affected members.

---

## 16. Deterministic validation

Validation covers, as applicable:

- policy active state;
- effective date inside policy;
- backdating limit;
- required member fields;
- valid plan;
- dependent/principal relationship;
- active duplicate employee number;
- duplicate Civil/National ID;
- duplicate passport;
- duplicate rows in the same endorsement;
- active-member lookup for deletion/termination/suspension;
- suspended-member lookup for reactivation;
- refund basis;
- reactivation date after suspension.

Blocking validation errors prevent progression.

For member-operated transaction types, zero member rows produce Needs Information and prevent advancement. Policy Cancellation is the exception because the system populates the affected population.

---

## 17. Refunds and premium impact

Member Deletion and Policy Cancellation support structured:

- FULL
- PRO_RATA

Financial calculations use Python Decimal.

The calculation snapshot retains the original premium, coverage dates, effective date, calculation basis/days and system calculated amount.

The TPA final amount is stored separately. If it differs from the system amount, an override reason is required.

AI never calculates or approves official financial values.

---

## 18. STP and approval

After authoritative validation, GLIS evaluates STP.

If eligible, the transaction records Auto Approved by STP and dispatches to TPA.

If approval is required, the transaction remains Pending Approval and reuses the GLIS approval infrastructure.

An approver can:

- approve;
- reject with reason;
- open an approval query/discussion;
- exchange multiple replies/files.

An unresolved Approval query blocks both approval and rejection.

---

## 19. Embedded conversations and visibility

Transaction discussions reuse TicketComment/TicketAttachment while rendering as compact conversation cards inside the TPA transaction.

Purposes:

- Approval
- TPA
- Client

Audiences:

- CLIENT_VISIBLE
- INSURER_TPA_INTERNAL
- SELECTED_PARTICIPANTS

Visibility is server-side.

### Internal insurer/TPA communication

Clients cannot see internal threads, internal metadata or internal attachments.

Authorized insurer/TPA staff can explicitly share a selected internal message body with the requester. The client then sees only the explicitly shared body in a separate shared-information area; the internal parent thread and internal files remain protected.

Protected query attachment downloads re-check message visibility/attachment authorization server-side.

---

## 20. TPA processing

After approval/STP:

1. transaction is dispatched to TPA;
2. authorized processor starts processing;
3. each row can record:
   - final card/member number;
   - TPA effective date;
   - TPA final premium/refund;
   - override reason;
   - comments/outcome;
4. TPA may open client-visible or internal discussions;
5. all open queries must be resolved before completion.

System amount and TPA final amount are always kept separate.

---

## 21. Suspension and reactivation

### Permanent termination

Permanent termination changes the active enrollment to Terminated at final processing and is not ordinary reactivation-eligible.

### Temporary suspension

MEMBER_SUSPEND changes the enrollment/member to Suspended at final TPA completion and stores suspension date/reason plus optional expected reactivation date.

### Reactivation

MEMBER_REACTIVATE requires an existing suspended enrollment. Validation confirms policy/date eligibility and final processing restores the enrollment/member to Active while recording the reactivation date.

---

## 22. Physical card dispatch

When the policy requires a physical card and the transaction is Member Addition, TPA completion enters Card Dispatch instead of immediately completing the endorsement.

Methods include:

- Courier;
- Hand Delivery;
- Collected by Client;
- Collected by Insurance Company;
- Collected from TPA;
- Other.

Statuses include:

- Pending;
- Ready for Dispatch;
- Dispatched;
- In Transit;
- Ready for Collection;
- Collected;
- Delivered;
- Failed / Returned;
- Not Required.

GLIS can record courier, AWB/tracking, dispatch/delivery dates, recipient/organization/contact, remarks and proof attachment.

The permanent member enrollment is finalized only after a terminal dispatch state (Delivered, Collected or explicitly Not Required).

Deletion, termination, suspension and policy cancellation do not use card dispatch.

---

## 23. Workflow status and activity

The transaction detail page contains a compact sticky Workflow Status panel on larger screens showing:

- current status/step;
- source;
- policy;
- requester;
- type;
- created/effective dates;
- STP;
- approval;
- TPA state;
- elapsed TAT;
- target TAT;
- refund basis where applicable.

The full-width Activity Timeline follows the workflow and records email receipt/classification/authority/policy matching, extraction/reprocessing, member corrections, validation, approval/query activity, TPA changes, card dispatch and completion.

---

## 24. Permissions

Important TPA permissions include:

| Permission | Purpose |
|---|---|
| tpa.view_tpa_dashboard | TPA workspace |
| tpa.create_enrollment | Initial enrollment |
| tpa.create_endorsement | Endorsements |
| tpa.terminate_member | Termination |
| tpa.delete_member | Deletion/Void |
| tpa.cancel_policy | Cancellation |
| tpa.approve_endorsement | Approval |
| tpa.process_endorsement | TPA processing |
| tpa.bypass_validation | Authorized bypass |
| tpa.override_premium | Authorized amount override |
| tpa.view_sensitive_member_data | Sensitive member data |
| tpa.view_ai_source_data | Source/AI payload |
| tpa.configure_tpa | TPA configuration |
| tpa.export_tpa_data | Export |

PolicyAccess additionally controls policy-scoped view/create/approve/process/premium rights.

Every HTMX/download endpoint still performs server-side authorization.

---

## 25. Deployment / validation

After pulling:

~~~bash
git pull origin main
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py makemigrations --check
python manage.py test apps.tpa
python manage.py runserver
~~~

Optional demo configuration:

~~~bash
python manage.py configure_tpa_ollama
python manage.py seed_tpa_sample --username YOUR_USERNAME
~~~

Primary routes:

~~~text
/portal/tpa/
/portal/tpa/policy-enrollment/
/portal/tpa/transactions/
/portal/tpa/inbound-emails/
/portal/tpa/guide/
~~~

---

## 26. Troubleshooting

### Office 365 not connected

Check Tenant ID, Client ID, secret, mailbox, Mail.Read application permission and admin consent. Use the Inbound Email monitor for the last synchronization error.

### Scheduler not running

Confirm <code>JOB_CENTER_ENABLED=True</code>, the **TPA Office365 Mailbox Sync** ScheduledJob is enabled and at least one Django process remains running. The monitor shows the effective cron and next run.

### Unauthorized sender

Create/review the sender's TPAEmailAuthority scope. Do not bypass authority with AI output.

### No vision provider

Ensure an active AIProviderConfig:

- allows sensitive data;
- supports vision;
- has <code>document_extraction</code> capability;
- points to an available model.

The failed source remains in Needs Review and can be reprocessed.

### JSON mapping failure

Ensure an active non-vision text provider has <code>member_field_mapping</code> and/or <code>email_extraction</code>. Review the extraction profile/training examples. Do not delete source evidence.

### Duplicate members

The manual modal and authoritative validation both check duplicates. Correct the identifiers or remove the duplicate source row rather than bypassing the rule.
