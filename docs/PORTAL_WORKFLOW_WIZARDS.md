# Portal workflow implementation report

TPA transaction detail now renders one selected business stage. The compact header,
native daisyUI stepper, and Previous/Next navigation remain visible around that
stage. Source payloads, row corrections, before/after details, and full audit
history remain in modals.

## Architecture and access

`apps/tpa/services/wizard.py` defines all stage names, status mappings, conditional
stages, navigation URLs, and the accessible frontier. It presents the existing
persisted transaction state; GET navigation never runs a new workflow action.
Transactions are still obtained through `visible_transactions(user)`, and POST
actions still use the existing access and workflow services. Reached stages can
be inspected by viewers; approval and processing authority are checked separately.

`/portal/tpa/transactions/<reference>/?step=<key>` supports full GETs, HTMX GETs,
deep links, and refresh. Future stages redirect to an accessible stage on normal
GET and return the accessible workspace on HTMX GET. Unknown or excluded stages
return a controlled 404. Closed transactions expose read-only information.
Validation cannot rewind a transaction already in TPA processing, and card
updates require an active card-dispatch stage.

`django-formtools` was considered. A second `WizardView` would duplicate the
persisted transaction state machine. The existing atomic creation forms continue
to use the lightweight creation helper and Django validation. Ticket creation
retains its existing session state, with server-side stage gating and invalidation
of downstream answers when earlier inputs change. No dependency or queue was added.

## Default stage and status mapping

| Persisted status | Default stage | Indicator / behavior |
| --- | --- | --- |
| `draft`, `extracting` | Intake & Correction | Later stages locked |
| Initial-enrollment `draft` | Policy & Benefit Plans | Intake also available |
| `pending_validation` | Validation | Approval and later stages locked |
| `needs_information` | Intake & Correction | Validation remains accessible with an error marker |
| `validation_failed` | Validation | Error marker and return-to-intake link |
| `pending_approval`, `approved`, `auto_approved` | Approval | Existing approval authority and ticket rules apply |
| `rejected` | Approval | Rejection details; closed/read-only |
| `sent_to_tpa`, `tpa_in_progress`, `processing` | TPA Processing | Existing processing authority applies |
| `tpa_query` | TPA Processing | Query marker |
| `failed` | TPA Processing | Error marker; closed/read-only |
| `card_dispatch` | Card Dispatch | Only for physical-card member additions |
| `processed`, `completed` | Complete | Final member, premium, TAT, SLA, and compact audit details |
| `cancelled` | Complete | Cancellation result; closed/read-only |

Policy & Benefit Plans exists only for `NEW_POLICY_ENROLLMENT`. Card Dispatch
exists only for `MEMBER_ADD` with `physical_card_required=True`; it is omitted
entirely otherwise. Open approval and TPA queries also mark their stages, respecting
the user's query visibility. Earlier accessible stages can be revisited; Next
never validates, approves, or completes a transaction.

## HTMX responses and actions

No new transaction route was needed. The existing detail endpoint accepts `step`.
Actions return `tpa/transaction/_workspace.html`, swapping `#transaction-workspace`
with `outerHTML` so the header, selected stage, stepper, and navigation update
together. GET responses use `HX-Push-Url`; actions use `HX-Replace-Url`. Forms carry
the selected `wizard_step`, while transitions deliberately select the relevant
new stage. Query replies and row updates retain their stage.

| Existing endpoint group, under `transactions/<reference>/` | Updated response behavior |
| --- | --- |
| `plans/add/` | Policy stage with a bound plan form on errors |
| `sources/upload/`, `sources/<id>/reprocess/`, `sources/<id>/delete/` | Intake workspace with upload/extraction feedback |
| `members/add/`, `members/upload/`, `members/select/`, `members/<id>/edit/`, `members/<id>/remove/` | Intake workspace; corrections and manual-entry errors reopen the relevant modal |
| `submit/`, `validate/` | Validation workspace and updated step availability |
| `approve/`, `reject/` | Updated workflow stage; rejection errors remain in the approval modal |
| `tpa/start/`, `tpa/items/<id>/`, `tpa/complete/`, `process/` | Processing rows with bound errors, then the appropriate dispatch/completion stage |
| Query creation, message, resolution, and sharing routes | Conversation updates inside Approval or TPA Processing |
| `card-dispatch/` | Bound dispatch errors or the final completion workspace |

Field errors are rendered inline. HTMX permission/lookup errors use an inline
workspace error response. Successful non-HTMX POSTs redirect to the selected stage;
invalid forms render the full page with bound errors. HTMX history restoration
requests receive the full portal shell. `Vary` covers both HTMX headers, and
`hx-history="false"` prevents sensitive workspaces from entering HTMX's local
snapshot cache.

## Shared loading and sidebar behavior

`portal.js` owns the common busy handler for HTMX POST forms, `data-processing-form`,
and existing `data-tpa-hx-form`. It disables associated submit buttons, shows native
daisyUI loading indicators and a live status, sets `aria-busy`, and restores original
control states on success, HTTP errors, aborts, timeouts, and network errors. A
workspace `hx-sync` drop policy and the busy guard prevent duplicate submissions.
Document uploads display an extraction-specific message. Network failures in a
modal display feedback inside that modal. No new asynchronous processing system
was introduced.

Sidebar overflow is managed globally in `portal.js`. The logo remains fixed and
the flexible navigation region uses `overflow-x: hidden`. Vertical overflow starts
hidden and becomes `auto` only when `scrollHeight > clientHeight`. ResizeObserver,
menu mutations, viewport changes, and drawer changes recalculate the state. The
duplicate TPA sidebar/busy handlers and obsolete custom spinner/stepper CSS were
removed.

HTMX swaps initialize dropzones, form conditionals, editors, modal restoration,
focus, and step centering. TPA ApexCharts instances are destroyed before their
containers are replaced and recreated after swaps or theme changes. Theme tokens
and native daisyUI states cover light/dark mode. The mobile stepper scrolls inside
its own container; it does not widen the page.

## Other portal processes

The existing three-stage endorsement creation helper now uses native daisyUI steps
and shared loading. Initial policy creation uses the same helper for Policy &
Routing, Period & Rules, and Benefit Plan & Create, with a no-JavaScript fallback.
The existing four-stage ticket creation flow now uses the shared stepper, HTMX,
loading feedback, history, server gating, and saved session state. Cascading ticket
selects explicitly swap their options with `innerHTML settle:0ms` and synchronize
their GET requests independently, so quick selections survive option replacement
and do not interfere with POST busy states.

Task lists/editing, dashboards, search/filter/list pages, ordinary ticket
conversations, and other one-screen forms were inspected and remain their existing
interfaces because they do not need an ordered creation wizard.

## Files changed

| Area | Files |
| --- | --- |
| Transaction presentation | `apps/tpa/services/wizard.py`, `apps/tpa/views.py`, `apps/tpa/forms.py`, `apps/tpa/middleware.py` |
| Migration graph | `apps/tpa/migrations/0012_merge_workflow_branches.py` |
| TPA templates | `templates/tpa/transaction_detail.html`, `templates/tpa/transaction/_workspace.html`, `_transaction_summary.html`, `_audit.html`, `_conversations.html`, and seven `steps/` partials |
| Shared components | `templates/components/workflow_wizard.html`, `workflow_nav.html`, `creation_wizard_form.html`, `form_errors.html`, `request_error.html`, `fragment.html` |
| Creation forms | `templates/tpa/policy_enrollment_form.html`, `templates/tpa/partials/transaction_wizard_form.html`, `manual_member_form.html`, `member_row_actions.html` |
| Tickets | `apps/tickets/views.py`, `apps/tickets/forms.py`, `templates/tickets/wizard/base.html`, and `step1.html` through `step4.html` |
| Global UI / assets | `templates/base_portal.html`, `static/js/portal.js`, `static/js/tpa.js`, `static/css/portal-polish.css`, `tpa-wizard.css`, `input.css`, compiled `output.css` |
| Regression tests | `apps/tpa/test_wizard.py`, `apps/tpa/tests.py`, `apps/tickets/tests.py` |
| Report | `docs/PORTAL_WORKFLOW_WIZARDS.md` |

## Verification and rollout

Regression coverage includes every status default, conditional stages, future-step
gating, permission/visibility checks, full versus partial GETs, history restoration,
read-only navigation, real CSRF checks, bound field errors, submit/validate/approve/
reject/start/query/dispatch/completion, creation forms, and global sidebar markup.

Commands used, with the project dependencies installed (Django 6.1.1 and Vanna 2.0.2):

```bash
python manage.py check
python manage.py test apps.tpa apps.tickets apps.tasks --noinput --verbosity 1
node --check static/js/portal.js
node --check static/js/tpa.js
git diff --check
static/css/tailwindcss -i static/css/input.css -o static/css/output.css --minify
python manage.py migrate --noinput --settings=glis_qa_settings
python manage.py makemigrations --check --dry-run
```

The full regression suite passed **93 tests**. Django checks and JavaScript syntax
checks passed. Fresh migrations succeeded in an isolated SQLite QA database with
scheduled jobs/mail disabled. The merge migration joins the repository's existing
two TPA migration leaves and performs no schema/data operations.

Local Chromium/Playwright checks used fabricated records and the project's existing
HTMX, ApexCharts, Alpine, and icon assets. They covered partial navigation, URL
persistence, Back/Forward, refresh, chart initialization, light/dark themes, 390px
mobile width and step visibility, sidebar fit/overflow and drawer behavior, bound
modal errors, spinner/aria-busy behavior, duplicate submission prevention, network
failure recovery, creation layouts, and the ticket wizard.

Deploy the committed static assets and run `python manage.py migrate` and
`python manage.py collectstatic --noinput` through the normal deployment process.
No live Ollama, external mail, courier, or production TPA integration was exercised.
GitHub's [Django UI validation](https://github.com/nasirsaikh/glis_enterprise_v3/actions/runs/36668153528)
and [TPA workflow tests](https://github.com/nasirsaikh/glis_enterprise_v3/actions/runs/36668153376)
passed. The [Django 6.1 compatibility check](https://github.com/nasirsaikh/glis_enterprise_v3/actions/runs/36668153690)
failed its migration-state step because it proposes migrations in unchanged
third-party `django_summernote` and `djangocms_alias` packages, and consequently
skipped its full-suite step. An isolated checkout of the original commit with
the pinned versions reproduces both third-party migration changes. These dependency migration
issues were not changed as part of the workflow UI refactor and remain a CI
blocker. The local 93-test suite and the independent TPA workflow check passed.
The existing test-fixture naive-datetime/static-directory warnings and scheduler
shutdown lock warning remain outside this UI change; the test process exits
successfully. The synchronous extraction services and business calculations retain
their existing behavior.
