# Global organizations and the unified request workflow

All policy enrollments and member endorsements have one required parent `Ticket`. Portal creation, email intake, collaboration, approvals, assignment, SLA tracking, notifications and audit history use the existing Ticket services. Medical validation, premium calculations and member processing remain domain services attached to that ticket.

## Implemented changes

| Area | Result |
| --- | --- |
| 1. Organization master | `accounts.Organization` replaces the TPA-specific organization table. Existing organization IDs and timestamps survive the migration. |
| 2. Organization types | Active, editable `OrganizationType` masters replace the fixed type field. Fifteen initial types and any historical custom codes are seeded. |
| 3. Organization structure | Parent organizations, contact details, address, tax information, configuration and notes are available. Model validation rejects hierarchy cycles. |
| 4. User memberships | Users and support groups can belong to multiple global organizations. Existing membership rows are retained. |
| 5. Scoped access | Role permissions are combined with organization membership, direct assignment, support-group membership and explicit sharing/approval participation. Global action permissions do not grant cross-organization browsing. |
| 6. Policy context | Policies reference global owners and insurers, a configured product and policy type, and generic processing organizations. The old policy TPA field is migrated to processing relationships. |
| 7. Benefit plans | Plans remain policy-specific and validate nonnegative values, date order and per-policy plan codes. Premium and sum-insured checks also exist in the database. |
| 8. Process configuration | Projects define request type, domain workflow key, authorized organization/types, prefix, reference format and product/category configuration. |
| 9. Reference generation | New requests receive atomic annual references from the project prefix. Historical ticket and transaction references are retained. |
| 10. Unified workspace | A common ticket header displays organization, policy, project, product and category. Domain steps appear inside the same ticket page. HTMX navigation returns one workspace and handles history restoration. |
| 11. Request creation | Create Request switches between service, policy, endorsement, claim, task and other requests. Policy context drives product/category choices; policy types come from product configuration. |
| 12. Assignment and ownership | Organization and support-group selectors restrict eligible staff on both GET and POST. Release preserves routing groups and other owners. Takeover locks the ticket and rejects an already-owned request. |
| 13. Tagged participants | Explicit tags give ticket visibility, notifications and audit events. Tagging alone does not grant assignment, status changes, domain processing or approval authority. |
| 14. Approval requests | Individual requests reuse `TicketApproval` alongside configured workflow steps. Request, decision and cancellation are audited. Duplicate pending requests are idempotent; only the assigned approver decides. |
| 15. Email intake | Enrollment, endorsements and claim intake use the shared request engine. Sender authority stays deterministic. Source emails reference the parent ticket; duplicate processed messages reuse the existing request. |
| 16. Migration and regression coverage | Populated upgrade and rollback tests cover identifiers, memberships, permissions, source documents, attachments, comments, policy access and previously orphaned transactions. Additional tests cover scope, forged selectors, approvals, ownership and browser rendering. |

## Before and after

| Area | Before | After |
| --- | --- | --- |
| Organizations | TPA-specific model | Global Accounts Organization |
| Sponsor | Separate field/concept | Removed from runtime architecture |
| User organizations | TPA organization mapping | Global multiple-organization memberships |
| TPA workflow | Transaction-centric screens | Required Ticket parent and common workspace |
| Policy enrollment | Separate TPA entry | POL Ticket |
| Member addition | Separate transaction reference | ADD Ticket |
| Member deletion | Separate transaction reference | DEL Ticket |
| Claims | Domain-specific intake | CLM Ticket |
| Assignment | Ticket/group assignment | Organization-aware validated selectors |
| Tagged users | Task-specific participation | Ticket-level tags |
| Approval | Configured steps | Configured and individual requests in one ledger |
| Release | Unassign operations | Current-owner release with retained groups/history |
| Takeover | Partial behavior | Atomic ownership with group permissions |
| SLA | Ticket and domain presentation | Shared Ticket SLA policies and deadlines |
| Audit | Separate domain events | Domain events mirrored into Ticket history |

## Organization types

Initial masters are Individual, Corporate, Insurance Company, Broker, Agent, Branch, Third Party Administrator, Service Provider, Healthcare Provider, Reinsurer, Surveyor / Loss Adjuster, Law Firm, Vendor, Internal Department and Other. Administrators can add types without changing Python choices or migrations.

Django admin exposes global Organizations and Organization Types under Accounts. Organization pages show linked users, support groups and policy/ticket counts. Users retain the old free-text profile organization solely for historical compatibility; current scope uses the global many-to-many memberships.

Deactivating a type or organization removes it from current memberships and intake selectors. A parent relationship describes structure and does not automatically grant access to child organizations.

## Projects and references

| Project | Request type | Workflow key | Default new reference |
| --- | --- | --- | --- |
| GLIS | Service Tickets | Standard ticket flow | `GLIS-YYYY-000001` |
| POL | Policies | `NEW_POLICY_ENROLLMENT` | `POL-YYYY-000001` |
| ADD | Endorsements | `MEMBER_ADD` | `ADD-YYYY-000001` |
| DEL | Endorsements | `MEMBER_DELETE` | `DEL-YYYY-000001` |
| TRM | Endorsements | `MEMBER_TERMINATE` | `TRM-YYYY-000001` |
| CHG | Endorsements | `MEMBER_UPDATE` | `CHG-YYYY-000001` |
| SUS | Endorsements | `MEMBER_SUSPEND` | `SUS-YYYY-000001` |
| REA | Endorsements | `MEMBER_REACTIVATE` | `REA-YYYY-000001` |
| CAN | Endorsements | `POLICY_CANCEL` | `CAN-YYYY-000001` |
| END | Endorsements | `GENERAL_ENDORSEMENT` | `END-YYYY-000001` |
| CLM | Claims | `CLAIM` | `CLM-YYYY-000001` |

`ticket_prefix` defaults to the project code. `reference_format` defaults to `{prefix}-{year}-{sequence:06d}` and must include all three keys. Prefixes are ASCII identifiers of at most 20 characters; the formatted reference is limited to 80 characters. A sequence belongs to a prefix and year, so projects sharing a prefix also share its counter.

Projects support any request type and can be added in admin. The listed domain keys connect the existing medical handlers. Other products and request types use configured Ticket categories, dynamic forms and approval workflows; adding a new deterministic domain processor still requires a corresponding domain implementation.

Each configured workflow needs an active product matching the policy product code and an active category for its workflow key. Missing or inactive configuration produces a controlled error and does not create an orphan ticket or a second workflow engine. Category SLA takes precedence over project SLA. Historical TPA categories carry their existing default routing, allowed requester groups, approval workflow and SLA into the new process projects.

Product `policy_types` is a JSON list of strings or objects, for example:

```json
[
  {"code": "GROUP_MEDICAL", "name": "Group Medical"},
  {"code": "INDIVIDUAL_MEDICAL", "name": "Individual Medical"}
]
```

Medical is configured initially. Additional product codes and policy types can be configured through existing Project, Product and Category admin pages.

## Access and collaboration

`TicketAccessPolicy.visible_queryset` is the common ticket boundary. A requester, assignee, authorized member of an assigned support group, active tagged participant, explicitly shared recipient or assigned approver can see the applicable request. Users with ticket browsing or domain configuration permissions see records in their active organizations. Existing per-user `PolicyAccess` entries remain supported and are bounded by newer profile memberships.

Visibility and action permissions are separate. A tag or pending approval grants visibility to that request. Edit, assignment, sensitive fields and domain intake/approval/processing retain their own server-side guards. Participant organization flags bound organization-based edit, assignment and approval permissions; direct ownership, group capabilities and explicit policy grants remain separate sources of authority.

The owner organization is initialized with edit/assignment participation, the insurer with approval participation, and configured processors with edit/assignment participation. Users still need the corresponding action permission. These flags do not grant all organization members the action automatically.

Assignment candidates come from organizations actually participating in the ticket, its active configured project groups and existing assigned groups. Adding an unrelated organization to a shared project does not add that organization's users to every ticket's selectors. Category `allowed_groups` controls requester access and refers to Django auth groups; it is not a support-group assignment allowlist. Legacy tickets without organization relationships retain their existing organization/support-group candidate scope.

Release removes only the acting owner's assignment. It retains other assignees, chooses a remaining primary owner when necessary, keeps support groups, records an audit event and notifies the routing group. Takeover is available to an eligible member of a group permitted to edit its tickets only when no owner remains. Both operations lock the same ticket row.

## One approval ledger

Configured steps and individual requests are records in `TicketApproval`. Individual requests have no configured step. Pending requests to the same user are reused, and completed decisions retain their timestamps, approver and note. The request creator can cancel a pending individual request; superusers can also cancel it.

Approval records are read-only in Django admin. Decisions, requests and cancellations use the portal service so the assigned actor, audit history and domain state stay consistent.

A final ticket decision advances a pending domain transaction. Manual domain decisions also write to this ledger. A pending ticket approval blocks manual domain approval. Open domain approval queries prevent dispatch until resolved. Once an approved request's last approval query is resolved, the same ticket decision resumes processing.

Validation and straight-through-processing eligibility remain deterministic domain checks. The Ticket approval service does not duplicate member eligibility, premium, refund or extraction logic.

## Upgrade and rollback

Apply the ordinary migration graph with the job center paused during the change window:

```bash
JOB_CENTER_ENABLED=0 python manage.py migrate --plan
JOB_CENTER_ENABLED=0 python manage.py migrate
JOB_CENTER_ENABLED=0 python manage.py check
JOB_CENTER_ENABLED=0 python manage.py makemigrations accounts core tickets tpa --check --dry-run
```

The upgrade performs these operations in dependency order:

1. Create the global type and organization masters, copy organizations with their existing primary keys, transfer direct/group organization admin permissions, and reseed database identity sequences.
2. Repoint user/support-group memberships and domain foreign keys while preserving membership rows. Rename policy/member/transaction sponsor fields to organization. Move the default processor setting to a generic global organization reference.
3. Create participation, tagging, reference counters and optional approval-step fields on the existing Ticket models.
4. Configure process projects and backfill policy products and processing relationships. Preserve existing linked ticket IDs and references, attach organization/policy context and create parent tickets only for legacy transactions without one.
5. Preserve legacy transaction references, reserve historical annual ticket counters, link source emails, and require a protected one-to-one parent ticket for every domain transaction.

The automated populated upgrade/rollback test checks old identifiers, timestamps, memberships, grants, comments, attachment paths, source document paths, member corrections and email links. Database migrations do not copy, move or delete file storage objects. Existing permission content types are retained for compatibility.

Take a database and media backup before a production migration. Rollback recreates the old organization table and restores old foreign keys, names and memberships. It selects the first configured processing organization for the old single-TPA field. New global type/hierarchy metadata cannot be represented fully in that older schema, so use the backup when an exact pre-upgrade restoration is needed. The supplied migration test covers a populated historical-schema round trip on SQLite.

For SQL Server deployments, rehearse the migration against a representative backup and inspect its filtered/nullable unique indexes and identity reseeding. SQLite cannot prove row-lock concurrency. The two concurrency tests are deliberately skipped on SQLite and run on databases with `SELECT FOR UPDATE` support.

## Validation

```bash
JOB_CENTER_ENABLED=0 python manage.py test
python -m compileall -q glis apps services
node --check static/js/tpa.js
node --test scripts/test_portal_ui.cjs
```

The browser tests require Playwright and Chromium. Set `PLAYWRIGHT_CHROMIUM_EXECUTABLE` when using an existing browser binary. Additional browser checks exercise actual Django-rendered request selectors and the unified ticket workspace in English/Arabic, desktop/mobile layouts and HTMX navigation.

Local verification on 1 October 2026 used Python 3.12, Django 6.1.1 and SQLite: the full suite ran 233 tests with 231 passing and the two row-lock concurrency tests skipped. The 29 unified-workflow tests also cover the final assignment lookup and cancellation-history fixes. Six existing Playwright UI tests and eleven live Django-rendered browser checks passed. All 106 repository templates compiled, application migration checks reported no changes, Django system checks passed, and the installed dependency resolver reported no broken requirements. The global migration check reports pre-existing drift in the third-party `djangocms_alias` package; application migration state is clean.

## Remaining boundaries

Claims and general endorsements use the configured ticket workflow; the medical transaction model remains responsible for the registered member and initial-enrollment handlers. This change does not introduce an automatic claim adjudication engine or deterministic business handlers for unrelated insurance products.

Historical references remain stable, so an upgraded transaction may keep a `TPA-END-…` reference while its canonical ticket reference has a different historical prefix. New domain transactions share their parent ticket's generated reference. Legacy URLs continue to resolve their transaction, and the portal navigates to the ticket workspace.

Production SQL Server race/DDL validation, external mailbox delivery and live AI provider responses require the deployment environment. The local suite verifies those integration contracts with mocks and populated SQLite migrations. Existing third-party CMS migration drift must be handled through those packages' own supported migrations; no vendor migrations are added to this refactor.
