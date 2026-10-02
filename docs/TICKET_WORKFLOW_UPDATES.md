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

The dashboard shows all seven KPIs in one row, which scrolls horizontally on narrow screens. Quick filters and the advanced filter modal apply consistently to KPIs, charts, recent tickets and the attention list while preserving the user's ticket scope.

Job Center admin status badges and registered handlers use argument-safe Django HTML formatting compatible with Django 6.1.
