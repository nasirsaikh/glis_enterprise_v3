# Greenline Insurance Services (GLIS) Enterprise Platform

GLIS is a bilingual, enterprise-grade insurance service, TPA member-management, workflow, document, task and analytics platform built on Django 6.1.1. It combines a public Greenline-style website with a secure authenticated portal for customers, corporate clients, insurers, TPAs, brokers, support teams, managers, auditors and administrators.

The platform is intentionally server-rendered and operationally simple: Django templates, HTMX and Alpine.js provide progressive enhancement; the authenticated portal uses Bootstrap 5.3.2 components; ApexCharts provides operational charts; APScheduler powers the built-in Job Center; Ollama is supported for local OCR, extraction and analytics; and Mayan EDMS can be used as the governed document engine.

> **Core design principle:** AI assists extraction, mapping, summarization and analytics. Eligibility, validation, pricing, approvals, permissions, workflow transitions and final insurance/TPA updates remain deterministic application logic.

---

## 1. Platform at a glance

| Capability | Current implementation |
|---|---|
| Public website | Bilingual English/Arabic site, RTL, CMS-managed content, services, network/provider content, downloads, contact information and theme support |
| Authenticated portal | Responsive Bootstrap workspace with light/dark/system modes, compact sidebar modes, notifications, profile and security settings |
| Service tickets | Multi-project/product/category request handling, assignment, groups, comments, attachments, dynamic forms, approvals, SLA/TAT, notifications and audit events |
| Task management | Manual tasks plus recurring task templates that create linked tickets automatically |
| TPA member management | Initial policy enrollment, member additions, terminations, deletion/void, policy cancellation, validation, pricing, approval, TPA processing and completion |
| Smart document intake | CSV/XLS/XLSX parsing, PDF/image OCR, multi-file evidence bundles and strict member JSON mapping |
| Email endorsements | IMAP ingestion of email body and attachments with AI extraction and the same downstream TPA workflow |
| AI configuration | Mock, Ollama, OpenAI-compatible/OpenAI and Anthropic provider configuration, extraction profiles, training examples and interaction audit |
| Analytics | Governed Vanna 2.0 analytics with Ollama/ChromaDB support, domain governance, SQL controls and user-scoped conversation history |
| Enterprise documents | Mayan EDMS integration for Document Center, ticket documents and controlled knowledge documents |
| Background jobs | Embedded APScheduler Job Center; no Celery/Redis/RabbitMQ required |
| CMS | django CMS plus GLIS configuration models for bilingual content, site settings and controlled navigation |
| API | Versioned <code>/api/v1/</code> routes, DRF, JWT support and schema tooling |
| Database | SQLite for development and SQL Server through <code>mssql-django</code> for production |
| Security | Server-side authorization, CSRF, CSP middleware, secure cookies, audit trails, sensitive-data controls and configurable AI data permissions |

---

## 2. Technology stack

### Backend

- Python 3.12 deployment baseline from <code>pyproject.toml</code>
- Django 6.1.1
- Django REST Framework
- django-allauth
- django CMS 5
- django-htmx
- django-filter
- drf-spectacular
- django-csp
- django-storages
- WhiteNoise
- APScheduler 3.11
- SQLite development database
- SQL Server production support through <code>mssql-django</code>

### Frontend

- Django templates
- HTMX 2.x
- Alpine.js CSP build
- Bootstrap 5.3.2 CSS and JavaScript bundle
- Bootstrap Icons
- ApexCharts
- responsive LTR/RTL layouts
- server-persisted user theme and sidebar preferences

### AI, OCR and analytics

- Ollama
- GLM-OCR or another configured vision-capable Ollama model for document OCR
- qwen2.5:7b or another configured text model for canonical JSON mapping
- Vanna 2.0.2
- ChromaDB
- configurable OpenAI-compatible/OpenAI and Anthropic providers
- AI extraction profiles and training examples managed from Django Admin

### Documents and file processing

- Mayan EDMS REST integration
- pypdf
- PyMuPDF
- openpyxl
- xlrd
- Pillow

---

## 3. High-level architecture

~~~mermaid
flowchart TB
    Public["Public GLIS Website<br/>django CMS / bilingual content"] --> Django["Django 6.1 Application"]
    Portal["Authenticated Portal<br/>Bootstrap + HTMX"] --> Django
    API["REST API / Integrations"] --> Django

    Django --> Tickets["Tickets / SLA / Approvals"]
    Django --> Tasks["Tasks / Recurring Tasks"]
    Django --> TPA["TPA Member Management"]
    Django --> Knowledge["Knowledge Base"]
    Django --> Analytics["Vanna Analytics"]
    Django --> JobCenter["APScheduler Job Center"]
    Django --> Documents["Document Gateway"]

    Tickets --> DB[("SQLite Dev / SQL Server Prod")]
    Tasks --> DB
    TPA --> DB
    Knowledge --> DB
    Analytics --> DB

    TPA --> AI["AI Provider Layer"]
    Analytics --> Ollama["Ollama / ChromaDB"]
    AI --> Ollama
    Documents --> Mayan["Mayan EDMS REST API"]
    JobCenter --> Mail["IMAP / HTTP / SQL / Python Jobs"]
~~~

---

## 4. Repository structure

| Area | Location | Responsibility |
|---|---|---|
| Project configuration | <code>glis/</code> | settings, URLs, WSGI/ASGI |
| Core | <code>apps/core/</code> | site configuration, audit, document gateway, shared models |
| Accounts | <code>apps/accounts/</code> | profiles, roles, social login policy, theme/sidebar preferences |
| Tickets | <code>apps/tickets/</code> | service requests, categories, dynamic forms, assignment, SLA, approvals, comments, attachments |
| Tasks | <code>apps/tasks/</code> | manual and recurring task management linked to tickets |
| TPA | <code>apps/tpa/</code> | policy enrollment, endorsements, members, OCR/AI intake, validation, pricing and TPA processing |
| AI | <code>apps/ai/</code> | provider configuration, extraction profiles, training examples and AI audit |
| Analytics | <code>apps/orchestrator/</code> | Vanna domains, SQL governance, prompts, training and query audits |
| Knowledge | <code>apps/knowledge/</code> | bilingual knowledge articles and controlled documentation |
| Job Center | <code>apps/job_center/</code> | embedded APScheduler, registered Python/SQL/API jobs and execution history |
| CMS | <code>apps/cms/</code>, django CMS | navigation, pages, public content and publishing |
| Services | <code>services/</code> | access rules, dynamic forms and datasource registry |
| Templates | <code>templates/</code> | public, portal, tickets, TPA, tasks, knowledge and document UI |
| Static assets | <code>static/</code> | Bootstrap assets and compact theme, brand CSS, portal JavaScript and TPA JavaScript |
| Documentation | <code>docs/</code> | TPA, frontend, compatibility and operational guides |

---

# 5. Frontend and design standard

The public pages and authenticated portal use **Bootstrap 5.3.2** with a compact theme adapted from the supplied [Course Planner reference](https://course-planner-140256174016.asia-south1.run.app/). Existing GLIS page structure, navigation, grids, workflows and Arabic support are retained.

~~~html
<section class="card">
  <div class="card-body">
    <span class="badge text-bg-primary">Status</span>
    <input class="form-control form-control-sm" aria-label="Subject">
    <button class="btn btn-primary btn-sm">Save</button>
  </div>
</section>
~~~

Bootstrap CSS, RTL CSS and the JavaScript bundle are pinned and committed locally. Shared template includes select the appropriate CSS for English or Arabic. The reference's reusable component rules and behavior are adapted in `static/css/style.css` and `static/js/main.js`; course-planner-specific routes and authentication scripts are not loaded.

No frontend CSS compilation is needed. Edit the Bootstrap markup and small GLIS styles, then run:

~~~bash
python scripts/check_bootstrap_assets.py
node --test scripts/test_portal_ui.cjs
python manage.py collectstatic --noinput
~~~

Browser regression tests require Playwright and Chromium in the development/CI environment. Production does not require Node.js/npm. See [Bootstrap UI](docs/BOOTSTRAP_UI.md) for asset provenance, modal/HTMX behavior, testing and deployment.

Use Bootstrap `card`, `badge`, `alert`, `table`, `nav`, `dropdown`, `modal`, `offcanvas`, `form-control`, `form-select`, `form-check-input` and `btn` components. Keep GLIS-specific step navigation, conversation messages and responsive grids in the shared semantic styles. The profile supports System, Light and Dark.

Sidebar modes:

- Full navigation
- Icon-only navigation
- Hidden navigation

The preference is stored per user.

---

# 6. Public website and CMS

GLIS includes a bilingual Greenline-style public website backed by django CMS and GLIS configuration models.

Public capabilities include:

- English and Arabic content;
- RTL rendering for Arabic;
- CMS-managed pages and content blocks;
- public services and medical TPA information;
- insurer/partner content;
- network-provider information;
- downloads and controlled documents;
- contact information;
- management/team content;
- theme-aware responsive layout;
- visitor tracking;
- login and portal entry points.

django CMS is available through the same Django deployment. Content editors can work with versioning/moderation/history plugins without changing the operational portal architecture.

---

# 7. Authentication, profiles and RBAC

Authentication supports Django credentials plus django-allauth social-provider integration for Google and Microsoft.

The user profile contains:

- role;
- organization;
- title and department;
- reporting manager;
- language preference;
- theme preference;
- sidebar mode;
- email/browser notification preferences;
- external-user status and approval state;
- optional guest-access expiry.

Current profile roles are:

| Role | Typical use |
|---|---|
| Super Admin | unrestricted platform administration |
| Admin | operational administration |
| Project Manager | team/project supervision |
| Support Agent | ticket handling |
| Requester/User | customer/internal requester |
| Viewer/Auditor | read/audit use |
| Guest | restricted external access |

Authorization is enforced server-side. Hiding a menu item is never considered sufficient access control.

---

# 8. Ticket and service-request management

The ticket platform is the workflow backbone used directly by service operations and indirectly by TPA transactions and recurring tasks.

## Ticket capabilities

- project → product → category hierarchy;
- ticket reference generation;
- requester and organization context;
- multiple assigned users;
- assignment to groups;
- group-member takeover;
- statuses and priorities;
- rich conversation/comments;
- internal/private notes where permitted;
- pasted screenshots and uploaded files;
- dynamic JSON-driven forms;
- required-document rules;
- secure sharing;
- export;
- AI-assisted ticket insights;
- related tickets;
- notifications;
- approvals;
- SLA/TAT tracking;
- event/audit history;
- HTMX partial updates.

## Statuses

The service workflow supports:

- New
- Open
- In Progress
- Pending Customer
- Resolved
- Closed

## SLA and TAT

Category/priority SLA policies can define:

- first-response target;
- resolution target;
- pause statuses;
- escalation timing;
- target users/groups;
- reporting-manager escalation;
- automatic close behavior.

Ticket exports include first-response TAT and resolution TAT in hours.

The Job Center can run recurring workflow processing so escalations and lifecycle automation do not depend on a separate Celery deployment.

---

# 9. Dynamic forms and datasource safety

Ticket forms can be defined through versioned JSON schemas and rendered as Django fields.

Supported patterns include:

- text and textarea;
- email and phone;
- numeric/currency;
- date/datetime;
- select and multiselect;
- radio/checkbox/switch;
- URL/tags/rating;
- conditional visibility;
- conditional required rules;
- role-aware visibility/editing;
- lookup-based choices;
- sensitive-field masking.

Editable schema JSON does **not** execute arbitrary SQL. Lookup sources must be registered in the server-side datasource registry.

Example:

~~~python
@DataSourceRegistry.register("approved_location_lookup")
def approved_location_lookup(*, user, params):
    return [("muscat", "Muscat")]
~~~

Production lookup implementations should use fixed reviewed queries, bound parameters, allowlisted outputs, least-privilege database credentials, timeouts and audit logging.

---

# 10. Task management

GLIS includes a ticket-integrated task workspace.

## Manual tasks

Users with the required permission can create, edit and soft-delete tasks from:

~~~text
/portal/tasks/
~~~

Each task carries:

- title and description;
- project/product/category;
- priority;
- owner;
- tagged users;
- due date;
- linked ticket;
- status inherited from the linked ticket.

## Recurring tasks

Administrators can define recurring templates with:

- owner;
- tagged users;
- project/product/category;
- priority;
- first due date;
- recurrence;
- number of calendar days before the due date to create the occurrence.

Supported recurrence patterns:

- daily;
- weekly;
- fortnightly;
- monthly;
- quarterly;
- half yearly;
- yearly;
- one time.

Each generated occurrence becomes a separate <code>Task</code> and a linked normal GLIS <code>Ticket</code>. A unique recurring-template/occurrence constraint prevents duplicate generation.

Manual diagnostics:

~~~bash
python manage.py generate_recurring_tasks
python manage.py generate_recurring_tasks --as-of 2026-09-29
~~~

The scheduled handler is designed to run through Job Center.

---

# 11. Enterprise document management with Mayan EDMS

GLIS remains the business application and user interface. Mayan EDMS is an optional document engine accessed through REST.

Implemented surfaces include:

- <code>/documents/</code> — enterprise Document Center;
- ticket-scoped managed documents;
- controlled knowledge documents;
- document search;
- upload;
- download;
- opening the full Mayan UI for permitted staff.

GLIS owns business authorization and workflow. Mayan owns document versions, OCR, document ACLs and document storage.

Recommended metadata convention:

~~~text
glis_object_type = ticket | claim | policy | legal | knowledge
glis_object_id   = GLIS primary key
glis_reference   = human-readable GLIS reference
uploaded_by      = GLIS user email
~~~

See <code>MAYAN_EDMS_INTEGRATION.md</code> for the full integration guide.

---

# 12. TPA Member Management / SmartEndorse workflow

The TPA module brings the SmartEndorse operating model directly into GLIS while reusing GLIS authentication, ticketing, SLA, approval, notification and audit infrastructure.

Primary routes:

~~~text
/portal/tpa/
/portal/tpa/policy-enrollment/
/portal/tpa/transactions/
/portal/tpa/inbound-emails/
/portal/tpa/guide/
~~~

## 12.1 Operating model

~~~mermaid
flowchart LR
    A["Intake & Correction"] --> B["Validation"]
    B --> C["Approval / STP"]
    C --> D["TPA Processing"]
    D --> E{"Query?"}
    E -- Yes --> F["Embedded Requester Chat"]
    F --> D
    E -- No --> G["Complete"]
~~~

AI is limited to source understanding and semantic extraction. Business decisions stay deterministic.

## 12.2 Supported organizations

Global organization types are editable masters shared across portal workflows. Initial types include Individual, Corporate, Insurance Company, TPA, Broker, Agent, Branch, Service Provider, Healthcare Provider, Reinsurer, Surveyor / Loss Adjuster, Law Firm, Vendor, Internal Department and Other.

Policy access can additionally be restricted by organization, policy and user.

## 12.3 Initial Policy Enrollment

A new policy starts in:

~~~text
Portal → Create Request → Policies
~~~

Initial setup creates the policy and a dedicated <code>NEW_POLICY_ENROLLMENT</code> transaction.

Select a policy number in this section to open its policy dashboard. It shows active/inactive members, coverage today, enrollment status, benefit-plan and principal/dependent distributions, and every visible endorsement with status filtering and pagination. Counts use one latest enrollment per member. Premium totals respect the policy's premium-view permission. The **Enrollment workflow** link opens the original onboarding wizard.

Before approval, authorized intake users can use **Edit details** on a request to correct its effective date, refund basis, reactivation date and remarks. Saving returns it to draft and clears old validation/pricing results. Policy is fixed, and the transaction type is fixed while member rows exist. **Delete draft** removes only an unprocessed draft endorsement; its audit and linked ticket are retained. Successful endorsement or initial policy completion automatically closes the linked GLIS ticket and records resolution/closure timestamps. Card dispatch continues to hold the request open until delivery or collection is complete.

The policy can contain:

- global owner organization;
- insurance company;
- configured processing organizations;
- policy period;
- currency;
- STP setting;
- premium-calculation setting;
- allowed backdating days;
- insurer/TPA references;
- one or more benefit plans.

Each plan can contain an annual premium, default sum insured and premium configuration.

The opening census can then be entered manually or loaded from structured files/PDF/images through the same source-document processor used for endorsements.

The policy becomes available as a completed enrollment only after the configured validation, approval/STP and TPA processing path is completed.

## 12.4 Endorsement types

Post-enrollment transactions support:

- Member Addition
- Member Termination
- Member Deletion / Void
- Policy Cancellation

Initial policy enrollment is deliberately separate from endorsement intake.

## 12.5 Member data

The canonical member model includes:

- TPA member ID;
- employee number;
- first/middle/last name;
- date of birth;
- gender;
- relationship;
- Civil/National ID;
- passport number;
- principal/dependent relationship;
- member status.

Relationships include:

- Principal
- Spouse
- Child
- Other

Dependents must resolve to a principal through the supported identifiers/relationships.

## 12.6 Unified source intake

The transaction workspace contains a single Source Documents & Ollama OCR intake area.

Up to 20 related files can be supplied as one evidence bundle so front/back ID images, passport pages and related evidence can be interpreted together.

| Source | Processing path |
|---|---|
| CSV | deterministic structured parsing |
| XLSX | deterministic structured parsing with openpyxl |
| XLS | deterministic structured parsing with xlrd |
| Text PDF | pypdf text extraction → text-model mapping |
| Scanned PDF | PyMuPDF page rendering → vision OCR → text-model mapping |
| PNG/JPG/JPEG/WEBP | vision OCR → text-model mapping |
| Manual portal entry | direct canonical member data |
| Email body | email extraction profile → canonical transaction/member data |
| Email attachments | same SourceDocument processor as portal uploads |

Source documents retain:

- original file name;
- extraction method;
- processing state;
- extracted payload;
- confidence;
- AI profile;
- source hash;
- processing error;
- uploader.

Submitted/extracted source values are preserved while corrected working values are stored separately for auditability.

## 12.7 OCR and LLM architecture

The recommended local pattern uses two different model responsibilities:

~~~mermaid
flowchart LR
    File["PDF / Image"] --> Vision["Vision OCR<br/>GLM-OCR"]
    Vision --> Text["OCR text"]
    Email["Email body"] --> Mapper["Text mapping model<br/>qwen2.5:7b"]
    Text --> Mapper
    Spreadsheet["CSV / XLS / XLSX"] --> Parser["Deterministic parser"]
    Parser --> Canonical["Canonical member JSON"]
    Mapper --> Canonical
    Canonical --> Validation["Deterministic validation/pricing"]
~~~

### Vision/OCR provider

Recommended configuration:

- provider: Ollama;
- model: <code>glm-ocr</code> or the exact installed quantized tag;
- <code>supports_vision=True</code>;
- capability: <code>document_extraction</code>;
- sensitive-data access only when approved.

### Text mapping provider

Recommended configuration:

- provider: Ollama;
- model: <code>qwen2.5:7b</code>;
- <code>supports_vision=False</code>;
- capabilities:
  - <code>member_field_mapping</code>
  - <code>email_extraction</code>
  - <code>structured_header_mapping</code>

The text model converts OCR/email evidence into strict JSON. It must not decide eligibility, premium, approval or STP.

### AI extraction administration

Django Admin supports:

- AI providers;
- task capabilities;
- vision flag;
- model endpoint/name;
- runtime options;
- timeout;
- provider priority;
- whether sensitive data is permitted;
- extraction profiles;
- field aliases;
- prompts/instructions;
- training examples.

This allows OCR/mapping prompts to be trained/configured without embedding every instruction in view code.

The mailbox monitor also provides **AI prompts & examples** to users with TPA or AI configuration permission. Create or select an email-extraction or attachment/OCR member-mapping profile; set product/type scope, instructions, aliases and examples of the expected JSON. Aliases can map labels such as Civil No/CPR to `national_id` and Policy No to `policy_number`. The first five active examples are included in their configured order. Type-specific email profiles are applied after classification when needed.

Use **Preview extraction** with sample email/OCR text to test the current prompt before saving. This creates no endorsement and changes no inbox message. **Coach AI on this email** copies an existing email body into the preview. Save the profile, then reprocess a failed/review email from its detail page. These are prompt-based instructions and examples, not model-weight training; authority checks, mandatory-field validation and approvals remain enforced.

## 12.8 Intake correction

Extracted and manually entered members appear in the same member matrix.

Authorized users can:

- review extracted values;
- correct rows;
- add rows;
- remove rows while the intake stage is editable;
- preserve source/submitted values;
- re-run validation after correction.

Before/after changes are recorded in the transaction event trail.

## 12.9 Validation

Deterministic validation covers the currently implemented rules including:

- required member fields;
- policy status/period;
- policy backdating limit;
- benefit-plan validity;
- duplicate identifiers;
- existing-member lookup for termination/deletion;
- principal/dependent rules;
- member identifier requirements;
- workflow-state eligibility.

Validation produces per-row errors/warnings plus transaction-level validation metrics.

## 12.10 Pricing and premium impact

Premium/refund calculation uses Decimal arithmetic and the configured benefit plan.

The transaction stores:

- premium before;
- premium adjustment;
- premium after;
- currency;
- row-level calculated premium;
- calculation snapshot.

AI does not calculate or override the official premium.

## 12.11 STP and approval

Policies can enable straight-through processing (STP).

The transaction records:

- validation score;
- STP eligible flag;
- STP blockers;
- approval state;
- approver and approval timestamp;
- rejection reason.

If the transaction qualifies for STP it can follow the configured auto-approval path. Otherwise it follows GLIS approval controls/manual authority.

Approval dispatches the transaction into the TPA processing stage; it does not bypass the final TPA completion rules.

## 12.12 TPA processing

Core processing statuses include:

- Sent to TPA
- TPA In Progress
- TPA Query
- Completed

An authorized TPA processor starts the transaction and can record per member:

- card/member number;
- TPA effective date;
- final TPA premium/refund amount;
- processing state/message.

For member additions and initial enrollment, the required final TPA fields must exist before completion.

Completion applies the deterministic member/enrollment updates and persists the TPA-final information.

## 12.13 Embedded TPA query chat

When TPA requires more information, the processor can raise a query.

The system:

1. creates a dedicated GLIS query ticket related to the transaction;
2. moves the transaction to TPA Query;
3. reuses normal TicketComment/TicketAttachment storage;
4. renders the conversation as compact conversation cards inside the TPA case;
5. keeps resolved conversations visible in history;
6. resumes processing when the query is resolved.

The user does not have to leave the TPA case to answer a query.

## 12.14 Automated Office 365 endorsement intake

Normal operation does **not** require a user to upload incoming email. Microsoft Graph v1.0 is the primary mailbox transport and runs through the embedded Job Center scheduler.

Flow:

~~~text
Office 365 Inbox
→ Graph delta synchronization
→ local immutable email/attachment evidence
→ endorsement classification
→ deterministic sender authority
→ policy resolution
→ body + attachment extraction
→ Intake & Correction
→ deterministic validation
→ STP / approval
→ TPA processing
→ optional query conversations
→ physical card dispatch when configured
→ completion
→ permanent member/policy update
~~~

The mailbox monitor is available at <code>/portal/tpa/inbound-emails/</code>. It shows connection/configuration state, the effective Job Center schedule, last attempt/success/error, next scheduled run, processed/review/ignored/failed counts and the inbound audit queue. **Sync Inbox Now** is permission-controlled; **Manual Intake / Reprocess** remains a fallback/recovery/testing path.

### Microsoft Graph application configuration

Create an Azure / Microsoft Entra app registration for server-to-server use:

1. Create an App Registration.
2. Add Microsoft Graph **Application** permission <code>Mail.Read</code>.
3. Grant tenant administrator consent.
4. Use <code>Mail.ReadWrite</code> only if a future workflow actually modifies messages in Microsoft 365.
5. Create a client secret or use the organization’s approved credential mechanism.
6. Restrict the application’s mailbox scope in Exchange/Entra where required by organizational security policy.
7. Put credentials in environment/secret management—never in Django Admin or the database.

~~~dotenv
TPA_MAIL_PROVIDER=office365_graph
TPA_MAIL_ENABLED=True
TPA_MAIL_AUTO_PROCESS_AI=True
TPA_MAIL_MAX_MESSAGES_PER_RUN=50
TPA_MAIL_SYNC_CRON=*/5 * * * *
TPA_MAIL_ACTOR_USERNAME=tpa-service-user

TPA_O365_TENANT_ID=00000000-0000-0000-0000-000000000000
TPA_O365_CLIENT_ID=00000000-0000-0000-0000-000000000000
TPA_O365_CLIENT_SECRET=use-a-secret-manager
TPA_O365_MAILBOX=endorsements@example.com
TPA_O365_FOLDER=Inbox
TPA_O365_RECEIVED_AFTER=
TPA_O365_TIMEOUT_SECONDS=60

TPA_EMAIL_CLASSIFICATION_MIN_CONFIDENCE=0.75
~~~

<code>TPA_MAIL_SYNC_CRON</code> overrides the seeded Job Center cron at runtime without storing secrets or creating a second scheduler. The default is every five minutes.

Graph polling uses delta synchronization and persists the delta link in <code>TPAMailboxSyncState</code>. Deduplication uses provider/message ID, mailbox/internetMessageId and attachment hashes so scheduler restarts/repeated runs do not create duplicate endorsements.

The legacy IMAP reader remains only as an explicit fallback by setting <code>TPA_MAIL_PROVIDER=imap</code> and configuring the existing <code>TPA_IMAP_*</code> values.

Manual diagnostics are still available:

~~~bash
python manage.py process_tpa_mailbox --username YOUR_USERNAME
python manage.py process_tpa_mailbox --username YOUR_USERNAME --no-ai
~~~

They are not required for normal scheduled operation.

### Sender authority

AI may extract a policy number, but AI does not grant authority. Configure <code>TPAEmailAuthority</code> in Django Admin to allow a sender for an organization/policy, transaction types and optional validity dates. Unauthorized senders are retained as evidence and routed to review rather than creating an actionable endorsement.

### Classification and evidence

Inbound evidence preserves Graph identifiers, internetMessageId, conversation ID, sender/To/CC, timestamps, text body, sanitized HTML, original attachments, hashes, AI output, provider/profile information, confidence and errors.

The strict extraction schema distinguishes Member Addition, Deletion, Permanent Termination, Temporary Suspension, Reactivation, Policy Cancellation, query/reply, unrelated mail and uncertain mail. Low-confidence/unrelated/unauthorized cases do not silently create production transactions.

## 12.15 TPA conversations, refund and card dispatch

Approval and TPA discussions use the existing GLIS TicketComment/TicketAttachment infrastructure but render inside the transaction as compact conversation cards.

Conversation audiences are enforced server-side:

- <code>CLIENT_VISIBLE</code>
- <code>INSURER_TPA_INTERNAL</code>
- <code>SELECTED_PARTICIPANTS</code>

An insurer/TPA internal thread is not visible to the client. Authorized internal staff can explicitly share a selected internal message body; that does **not** expose the parent internal thread or its internal attachments.

Selected-participant discussions use an explicit participant list and notify only those selected users. Intake mutation is separately authorized from transaction visibility, so read-only policy users cannot upload/reprocess/delete evidence, add/edit/remove members, select members or submit workflow changes by posting directly to an endpoint.

Failed/review-required **manual** evidence can be removed during the editable intake stage; Office365/email-linked evidence is preserved for audit and can only be reprocessed or supplemented. Inbound-email audit records also persist the AI provider and model name used for extraction.

Deletion and Policy Cancellation use structured refund basis <code>FULL</code> or <code>PRO_RATA</code>. Calculations use <code>Decimal</code> and retain calculation snapshots. System-calculated amounts and TPA-final amounts remain distinct and an override reason is required when they differ.

Temporary suspension and reactivation are first-class transaction types. Permanent termination remains distinct and cannot be treated as an ordinary temporary suspension.

For Member Addition, when <code>Policy.physical_card_required</code> is enabled, successful TPA processing enters the Card Dispatch step instead of prematurely completing. Courier/delivery/collection status, AWB/tracking, dates, recipient details, remarks and proof are auditable. Deletion, termination, suspension and policy cancellation do not require card dispatch.

## 12.16 TPA permissions



Model permissions include:

| Permission | Purpose |
|---|---|
| <code>view_tpa_dashboard</code> | access TPA dashboard |
| <code>create_enrollment</code> | create initial enrollment |
| <code>create_endorsement</code> | create endorsements |
| <code>terminate_member</code> | terminate member |
| <code>delete_member</code> | delete/void member |
| <code>cancel_policy</code> | cancel policy |
| <code>approve_endorsement</code> | approve transaction |
| <code>process_endorsement</code> | TPA processing |
| <code>bypass_validation</code> | authorized validation bypass |
| <code>override_premium</code> | authorized premium override |
| <code>view_sensitive_member_data</code> | sensitive member access |
| <code>view_ai_source_data</code> | raw AI/source data access |
| <code>configure_tpa</code> | TPA configuration |
| <code>export_tpa_data</code> | export authority |

<code>PolicyAccess</code> additionally controls policy-scoped rights such as view, member visibility, enrollment creation, endorsement creation, premium visibility, approval and processing.

---

# 13. AI assistance outside TPA

The general ticket workspace contains assistive AI capabilities such as:

- summary;
- priority suggestion;
- group/category suggestion;
- similar-ticket assistance;
- knowledge suggestion;
- clarification questions.

General AI settings are configurable and interaction records are auditable.

The default mock provider is deterministic and suitable for local/demo operation. Real provider use should be enabled only after privacy, data-residency, retention and security approval.

---

# 14. Governed Vanna analytics

GLIS contains a governed Vanna analytics workspace rather than exposing unrestricted natural-language SQL.

The analytics architecture supports:

- Vanna 2.0;
- local Ollama model;
- ChromaDB retrieval memory;
- configurable domains;
- datasource metadata;
- business rules;
- table policies;
- column policies;
- role-based column overrides;
- row access policies;
- suggested prompts;
- versioned training prompts;
- training candidates/examples;
- conversation sessions;
- SQL/query audit;
- preview/export;
- query duration/status diagnostics.

Typical local models:

~~~bash
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text
ollama serve
~~~

Typical environment values:

~~~dotenv
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5-coder:7b
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_CONTEXT_WINDOW=8192
OLLAMA_TEMPERATURE=0.1
VANNA_DB_SCHEMA=main
CHROMA_PERSIST_DIRECTORY=data/chroma
~~~

For SQL Server, configure the governed datasource and schema appropriately rather than allowing arbitrary editable SQL.

---

# 15. Job Center / APScheduler

GLIS includes a Hangfire-style scheduler application based on APScheduler.

It intentionally requires:

- no Redis;
- no RabbitMQ;
- no Celery worker;
- no Celery Beat;
- no separate scheduler management command.

The scheduler starts with Django and uses a database-backed leader lock to reduce duplicate scheduling across multiple web workers.

Supported job types include:

- registered Python functions;
- SQL queries;
- stored procedures;
- HTTP/API calls.

Operational features include:

- cron schedules;
- manual Run now;
- retry handling;
- timeout recording;
- execution history;
- error and traceback logging;
- Admin management;
- staff-only API surfaces.

Important settings:

~~~python
JOB_CENTER_ENABLED = True
JOB_CENTER_MAX_WORKERS = 10
~~~

Use the registry pattern for Python jobs rather than storing arbitrary Python code in the database.

---

# 16. Localization and RTL

GLIS is configured for:

- English: <code>en</code>
- Arabic: <code>ar</code>
- timezone: <code>Asia/Muscat</code>

The portal and public site set the document direction from the active language.

Translation workflow:

~~~bash
python manage.py makemessages -l ar
python manage.py compilemessages -l ar
~~~

New UI should use Django translation tags and logical layout properties so Arabic remains first-class.

---

# 17. Local installation

## 17.1 Prerequisites

Recommended:

- Python 3.12.x for deployment compatibility;
- Git;
- optional SQL Server ODBC Driver 18;
- optional Ollama for AI/OCR/Vanna;
- optional Mayan EDMS for enterprise documents.

Create the environment:

~~~bash
python -m venv .venv
~~~

Windows PowerShell:

~~~powershell
.venv\Scripts\Activate.ps1
~~~

Linux/macOS:

~~~bash
source .venv/bin/activate
~~~

Install dependencies:

~~~bash
python -m pip install --upgrade pip
pip install -r requirements.txt
~~~

Then:

~~~bash
python manage.py migrate
python manage.py check
python manage.py runserver
~~~

Open:

~~~text
Public website: http://127.0.0.1:8000/
Portal:         http://127.0.0.1:8000/portal/
TPA:            http://127.0.0.1:8000/portal/tpa/
Tasks:          http://127.0.0.1:8000/portal/tasks/
Analytics:      http://127.0.0.1:8000/analytics/
Documents:      http://127.0.0.1:8000/documents/
Admin:          http://127.0.0.1:8000/admin/
~~~

---

# 18. TPA local setup

Install the local OCR and text models:

~~~bash
ollama pull glm-ocr
ollama pull qwen2.5:7b
ollama serve
~~~

Configure TPA providers/profiles:

~~~bash
python manage.py configure_tpa_ollama
~~~

Optional exact OCR tag:

~~~bash
python manage.py configure_tpa_ollama --ocr-model glm-ocr:q8_0 --text-model qwen2.5:7b
~~~

Create sample TPA data:

~~~bash
python manage.py seed_tpa_sample --username YOUR_USERNAME
~~~

The sample command creates/updates demo organizations, policy, plans, family/member data, access rights and the local TPA AI configuration used for development.

---

# 19. Database configuration

## SQLite development

SQLite is the default development database.

~~~bash
python manage.py migrate
~~~

## SQL Server

Install Microsoft ODBC Driver 18 and configure:

~~~dotenv
DATABASE_ENGINE=mssql
DATABASE_NAME=GLIS
DATABASE_HOST=sqlserver.internal
DATABASE_PORT=1433
DATABASE_USER=glis_app
DATABASE_PASSWORD=use-a-secret-manager
DATABASE_DRIVER=ODBC Driver 18 for SQL Server
DATABASE_EXTRA_PARAMS=TrustServerCertificate=no;Encrypt=yes
~~~

Use a dedicated least-privilege database account and validate migrations against staging before production rollout.

---

# 20. Mayan EDMS configuration

Example:

~~~dotenv
MAYAN_ENABLED=True
MAYAN_BASE_URL=http://127.0.0.1:8090
MAYAN_API_TOKEN=
MAYAN_API_USERNAME=glis_service
MAYAN_API_PASSWORD=change-me
MAYAN_VERIFY_SSL=True
MAYAN_TIMEOUT=45
MAYAN_UPLOAD_PATH=/api/v4/sources/<SOURCE_ID>/actions/<ACTION_ID>/execute/
MAYAN_SEARCH_PATH=/api/v4/search/search_models/documents.Document/
MAYAN_DOWNLOAD_PATH=/api/v4/documents/{document_id}/files/1/download/
MAYAN_DOCUMENT_UI_PATH=/#/documents/{document_id}/
~~~

Deploy Mayan independently. Do not add Mayan applications to GLIS <code>INSTALLED_APPS</code> and do not share the GLIS application database with Mayan.

---

# 21. Static files and deployment

Development can run directly through Django.

Production static collection:

~~~bash
python manage.py collectstatic --noinput
~~~

Production example with Gunicorn:

~~~bash
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn glis.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 90
~~~

Terminate TLS at the approved reverse proxy and configure forwarded protocol/host handling correctly.

Because Job Center runs inside Django, at least one application process must remain continuously running for scheduled jobs to execute.

---

# 22. Security baseline

The repository includes or is structured around:

- Django CSRF protection;
- secure/HTTP-only cookies in production;
- HTTPS/HSTS configuration;
- CSP middleware;
- same-origin framing support required by django CMS;
- server-side object authorization;
- permission-filtered ticket access;
- policy-scoped TPA access;
- AI sensitive-data controls;
- environment/secret references instead of storing provider secrets in editable models;
- audit/event records;
- sanitized rich-text handling;
- controlled datasource registry;
- no arbitrary SQL from dynamic form JSON;
- Mayan least-privilege service-account integration.

Before real insurance/identity data is processed in production, also implement the organization’s requirements for:

- private object/media storage;
- malware scanning;
- backup/restore testing;
- SIEM/centralized logging;
- rate limiting;
- credential rotation;
- data retention/deletion;
- privacy impact assessment;
- AI provider approval and data residency;
- vulnerability/dependency scanning.

---

# 23. Testing and validation

General checks:

~~~bash
python manage.py check
python manage.py makemigrations --check
python manage.py test
python -m compileall apps glis services
~~~

TPA regression suite:

~~~bash
python manage.py test apps.tpa
~~~

Task suite:

~~~bash
python manage.py test apps.tasks
~~~

Frontend verification runs <code>scripts/check_bootstrap_assets.py</code> and the Playwright UI regression suite to verify the committed Bootstrap assets, compact layouts and interaction behavior.

---

# 24. Main routes

| Route | Purpose |
|---|---|
| <code>/</code> | public website |
| <code>/portal/</code> | authenticated dashboard |
| <code>/portal/tickets/</code> | service tickets |
| <code>/portal/tasks/</code> | task management |
| <code>/portal/tpa/</code> | TPA dashboard |
| <code>/portal/tpa/policy-enrollment/</code> | initial policy enrollment |
| <code>/portal/tpa/transactions/</code> | endorsement/TPA pipeline |
| <code>/portal/tpa/inbound-emails/</code> | email intake |
| <code>/portal/tpa/guide/</code> | in-application TPA guide |
| <code>/documents/</code> | Mayan-backed Document Center |
| <code>/knowledge/</code> | knowledge base |
| <code>/analytics/</code> | governed Vanna analytics |
| <code>/api/v1/</code> | application API |
| <code>/job-center/</code> | Job Center API surfaces |
| <code>/admin/</code> | Django administration |

---

# 25. Development rules

When extending GLIS:

1. Reuse existing apps/services before creating duplicate business concepts.
2. Enforce authorization in views/services, not only templates.
3. Keep public and operational UI on Bootstrap 5.3.2.
4. Prefer Bootstrap components and shared GLIS semantic styles.
5. Use ApexCharts for new portal charts.
6. Use HTMX for targeted server updates rather than introducing a SPA framework.
7. Keep AI advisory/extractive; deterministic insurance rules stay in Python/services.
8. Preserve source, corrected and final values when auditability matters.
9. Never put executable SQL or secrets inside editable JSON/configuration.
10. Register background Python jobs through Job Center’s safe registry.
11. Keep English/Arabic and RTL behavior in every new user-facing module.
12. Add regression tests for workflow/status/permission changes.

---

# 26. Current scope and extension points

The repository currently provides strong foundations for service operations, medical TPA member administration, enterprise documents, tasks, analytics and AI-assisted intake.

Some broader insurance workflows may be represented today as service categories/content/integration hooks rather than dedicated transactional applications. In particular, do not assume that a public “Claims Management” service description is the same as a complete claim-registration/adjudication/reinsurance/settlement engine.

Future dedicated business modules should reuse the existing platform services for:

- identity and RBAC;
- tickets and SLA;
- approvals;
- notification/audit;
- Mayan document metadata;
- Job Center;
- AI provider governance;
- dynamic forms;
- analytics governance.

This avoids creating separate workflow engines for claims, policy servicing, legal, complaints or other insurance domains.

---

# 27. Additional documentation

Important repository guides:

- <code>docs/TPA_USER_GUIDE.md</code> — detailed TPA operating guide
- <code>docs/BOOTSTRAP_UI.md</code> — compact Bootstrap components, assets and deployment
- <code>apps/job_center/README.md</code> — scheduler architecture and job registration
- <code>MAYAN_EDMS_INTEGRATION.md</code> — document integration
- <code>DJANGO_CMS_MIGRATION.md</code> — CMS migration notes
- <code>docs/DJANGO_6_1_COMPATIBILITY.md</code> — framework/dependency compatibility

---

# 28. Recommended production rollout sequence

1. Configure production secrets and <code>DEBUG=False</code>.
2. Configure SQL Server and validate migrations on staging.
3. Configure HTTPS, trusted origins, proxy headers and secure cookies.
4. Run <code>collectstatic</code>.
5. Review RBAC, groups and policy-level TPA permissions.
6. Configure email delivery and, if required, IMAP endorsement intake.
7. Configure Ollama or an approved AI provider; validate sensitive-data rules.
8. Configure Mayan EDMS if enterprise document governance is required.
9. Validate Job Center leadership and scheduled jobs in the real deployment topology.
10. Run all automated tests and business UAT.
11. Test English, Arabic, RTL, light and dark themes.
12. Test TPA enrollment → validation → approval → TPA processing → completion end to end.
13. Test query chat, attachments, email intake and OCR evidence bundles.
14. Validate backup, restore, monitoring and incident procedures.
15. Remove/rotate development credentials and sample data before go-live.

---

## Project objective

GLIS is intended to provide one consistent insurance-service platform rather than a collection of disconnected portals: a modern public site, a role-based operational workspace, shared workflow/SLA services, governed documents, AI-assisted intake, deterministic insurance processing, TPA member administration, recurring work management and governed analytics — all within the existing Django architecture.


## Global organizations and unified requests

Policy enrollment, endorsements and claims use the existing Ticket engine. Organizations and organization types are global Accounts masters. Create Request chooses a configured process; Tickets provides scoped request-type tabs, a common workspace, assignment/release/takeover, tagging and one approval ledger.

See [the architecture, migration and implementation checklist](docs/UNIFIED_WORKFLOW.md) for the complete change map, default prefixes, configuration, rollback behavior, test commands and deployment boundaries.
