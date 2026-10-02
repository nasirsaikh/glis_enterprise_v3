# Ticket workflow configuration

Apply the new migration and refresh static files after pulling:

```sh
git pull origin main
python manage.py migrate
python manage.py collectstatic --noinput
```

Restart the Django application after deploying the code and assets.

## Category rules

| Setting | Behavior |
| --- | --- |
| Attachment required during ticket creation | Requires at least one file before submission. Individual named document rules still apply. |
| Attachment required during comments | Requires a file on each comment. When disabled, comments may still include optional files subject to the category's extension, size and count limits. |
| Reopen allowed days | Reopen is offered and permitted until this many days after `closed_at`. `0` disables reopening. |

Existing comment requirements are preserved by the migration. The creation requirement defaults to off. Configure each flag independently in category administration.

## Approval and activity

While approval is pending, rejected or awaiting information, the creator and members/managers of their active support team can comment and close the ticket. Normal ticket visibility rules still apply; superusers retain administrative access. Other participants use their assigned approval action.

Approvers can approve, reject or request additional information. Rejection and information requests require an explanatory note in the portal. The creator/team supplies a response with **Resubmit to approver**. Previously successful decisions remain approved; blocked decisions return to pending at their existing step. Both the original decision and the response remain in the activity history.

Closing pauses approval and linked TPA actions. Reopening restores the saved status without rebuilding the approval sequence. A linked endorsement rejected by its ticket approver can reopen, resubmit and continue approval. Direct editing of approval records in admin is disabled so decisions always use the shared workflow and its ledger.

Comments and activity records appear together in timestamp order, including creation, assignments, tags, approval requests/decisions, resubmission, attachments, edits, closure, reopening, SLA events and TPA transitions. Internal records retain their visibility restrictions. The comment status selector excludes **New** and offers only authorized transitions.

## Portal controls

Native selects gain an in-menu search field with keyboard support, including dependent HTMX fields and multi-selects. Django admin autocomplete and its existing filtered multi-select widgets retain their built-in search. English/Arabic labels and light/dark colors are supported.

User avatars display uploaded profile photos, with initials as a fallback. Rich-text editors support Expand/Collapse and vertical resizing without clearing the draft.

Search controls initialize after HTMX finishes restoring field attributes, and
replayed scripts, modal reopening and cached history reuse a single control per
select. Refreshed assets include version identifiers to clear older cached files.

The dashboard shows all seven KPIs in one row, which scrolls horizontally on narrow screens. Quick filters and the advanced filter modal apply consistently to KPIs, charts, recent tickets and the attention list while preserving the user's ticket scope.

Advanced filters include projects, products, categories/subcategories, request types,
statuses, priorities, organizations/types, policies, requesters, assignees, support
groups, approvers, approval states, visibility, all six SLA states, SLA policies
and creation dates. Lookup options combine accessible configuration with values
on visible requests, including historical/inactive records. Unrelated private
requests do not contribute options. Multiple values within one filter are ORed;
different filters are ANDed. Quick project/status controls and their modal copies
share the same selection and submit each value once.

Portal multi-selects use locally bundled Bootstrap Multiselect v2.0.0 with search,
checkboxes and **Select all results** (which applies to the current search).
Assignments, task tags and dynamic multiselect fields use the same control. The
private jQuery instance preserves existing Django/CMS globals; native values,
required-field validation and HTMX events remain intact.

Job Center admin status badges and registered handlers use argument-safe Django HTML formatting compatible with Django 6.1.

## Activity emails and live updates

Each committed ticket activity queues an individual HTML email with a plain-text
alternative, the visible comment/action history and the applicable process flow.
Member corrections, evidence extraction and other TPA activities also enter the
ticket ledger. API edits, assignments, comments and status actions use this ledger.
Private notes and workflow discussions retain their recipient access rules.

Category **Send initial email** controls creation and initial approval activity;
**Send update email** controls later activities. Both settings are checked again
when the queued job runs. Recipients include the requester and their active team, current assignees,
assigned group members/managers, approvers, active tagged users, task watchers
and unexpired share recipients who still have access. Users without an email,
inactive/unapproved/locked accounts, expired guest accounts and users who opted
out of activity email are excluded. Emails are addressed individually.

The ticket, embedded TPA workspace and task edit form check for changes every two
seconds while visible. Clean ticket pages refresh automatically. Open dialogs and
unsaved forms display a reload notice and preserve the draft. Portal submissions
carry a record revision; the server locks the ticket and rejects stale submissions
with HTTP 409. Invalid forms do not create a new revision. Legacy integrations
without a revision remain supported.

## Intake and public-page controls

Source files accumulate across separate browse/drop actions. The selected list
shows filenames, sizes and Remove buttons. The editor starts with five rows and
supports Expand/Collapse and vertical resizing. Ticket comment history scrolls
within 200px; the collapsed message editor is also capped at 200px and can expand.
Vanna uses the same editor and
submits readable question text. Task watchers and ticket tags support searchable
selection of multiple users. Replaced dependent selects remove the old control.

The intake **Validated** and **Errors / Needs Correction** tabs display their
success and error row counts. Success includes valid rows and rows with warnings.
Policy creation shows **Policy & Routing**, **Period & Rules**, and **Benefit
Plans & Create** one step at a time. A validation error returns to its relevant
step and retains the entered values and benefit plan controls.
Removed benefit-plan rows stay hidden and do not affect validation or the step
chosen for remaining errors.

**Parent / Principal** does not ask for a parent. Spouse, child and other dependents
must select an existing principal on the policy or a principal row already in the
transaction, in both manual intake and correction. OCR, email and spreadsheet
intake resolve active benefit plans by code, name, display label or database ID
within the selected policy. Ambiguous or unmatched references require correction.

Automatic approvals display **Auto approved by System**. The separate TPA new
discussion form is hidden for requests linked to a ticket; existing discussion
history remains accessible. Public CMS submenus use Bootstrap dropdown controls.
The provider network opens in a large, scrollable modal with its existing filters.

## Password recovery

**Forgot password** offers an **Email reset link** or **Email one-time code (OTP)**.
Links use Django's expiring, single-use password reset tokens. The six-digit OTP
expires after 10 minutes, is bound to the requesting session, permits five failed
attempts and is consumed after a successful password reset. Enter the code in six
single-digit boxes first; **Verify code** opens the separate password-change step
only after successful server verification. Pasting the full code and keyboard
navigation are supported. The verified step remains bound to the session and
original code expiry. A password change or
account lock invalidates outstanding recovery attempts. Both methods use common
request throttling and generic responses for unknown/ineligible addresses.
Security recovery email is independent of activity-email preferences and category
flags. Successful recovery returns to sign-in without automatically signing in.

Deploy accounts migrations through `0008` and tickets migration `0011`, refresh static files
and restart Django. Set `SITE_URL` to the real public origin, configure the existing
SMTP settings and keep Job Center enabled: its queue worker delivers ticket and
recovery emails. The account profile administration now exposes **Is locked**,
which blocks sign-in, existing portal sessions, recovery and activity email.
