"""Presentation of the persisted workflow; navigation never changes its state."""

from django.http import Http404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from ..models import MemberTransaction, TransactionQuery
from .access import visible_transaction_queries


Status = MemberTransaction.Status
STEP_DEFINITIONS = (
    ("policy_setup", _("Policy & Benefit Plans"), "bi-building-add"),
    ("intake", _("Intake & Correction"), "bi-inbox"),
    ("validation", _("Validation"), "bi-shield-check"),
    ("approval", _("Approval"), "bi-check2-square"),
    ("tpa_processing", _("TPA Processing"), "bi-people"),
    ("card_dispatch", _("Card Dispatch"), "bi-truck"),
    ("complete", _("Complete"), "bi-check2-circle"),
)
STATUS_STEPS = {
    Status.DRAFT: "intake",
    Status.EXTRACTING: "intake",
    Status.PENDING_VALIDATION: "validation",
    Status.NEEDS_INFORMATION: "validation",
    Status.VALIDATION_FAILED: "validation",
    Status.PENDING_APPROVAL: "approval",
    Status.APPROVED: "approval",
    Status.AUTO_APPROVED: "approval",
    Status.REJECTED: "approval",
    Status.SENT_TO_TPA: "tpa_processing",
    Status.TPA_IN_PROGRESS: "tpa_processing",
    Status.TPA_QUERY: "tpa_processing",
    Status.PROCESSING: "tpa_processing",
    Status.FAILED: "tpa_processing",
    Status.CARD_DISPATCH: "card_dispatch",
    Status.PROCESSED: "complete",
    Status.COMPLETED: "complete",
    Status.CANCELLED: "complete",
}
CLOSED_STATUSES = {
    Status.PROCESSED, Status.COMPLETED, Status.REJECTED,
    Status.FAILED, Status.CANCELLED,
}


def transaction_step_url(tx, key):
    return f"{reverse('tpa:transaction_detail', args=[tx.reference])}?step={key}"


def get_transaction_steps(tx, user):
    """The caller must first obtain tx through visible_transactions(user).

    View access is intentionally independent of approval/processing authority:
    clients can inspect reached stages, while existing action guards decide who
    may change them. Unreached stages stay locked for every role.
    """
    initial_setup = tx.transaction_type == tx.Type.NEW_POLICY_ENROLLMENT
    requires_dispatch = (
        tx.transaction_type == tx.Type.MEMBER_ADD and tx.physical_card_required
    )
    definitions = [
        item for item in STEP_DEFINITIONS
        if (item[0] != "policy_setup" or initial_setup)
        and (item[0] != "card_dispatch" or requires_dispatch)
    ]
    keys = [item[0] for item in definitions]
    current = STATUS_STEPS.get(tx.status, "intake")
    if current == "card_dispatch" and not requires_dispatch:
        current = "tpa_processing"
    frontier = keys.index(current)
    successful = tx.status in {Status.PROCESSED, Status.COMPLETED}
    failed_step = {
        Status.NEEDS_INFORMATION: "validation",
        Status.VALIDATION_FAILED: "validation",
        Status.REJECTED: "approval",
        Status.FAILED: "tpa_processing",
    }.get(tx.status)
    open_queries = set(visible_transaction_queries(user, tx).filter(
        status=TransactionQuery.Status.OPEN
    ).values_list("purpose", flat=True))
    return [
        {
            "key": key, "label": label, "icon": icon,
            "template": f"tpa/transaction/steps/_{key}.html",
            "url": transaction_step_url(tx, key),
            "accessible": bool(user.is_authenticated and index <= frontier),
            "completed": tx.status != Status.CANCELLED and (
                index < frontier or (key == "complete" and successful)
            ),
            "current": key == current,
            "has_error": key == failed_step,
            "has_query": (
                key == "approval" and TransactionQuery.Purpose.APPROVAL in open_queries
            ) or (key == "tpa_processing" and (
                tx.status == Status.TPA_QUERY or TransactionQuery.Purpose.TPA in open_queries
            )),
        }
        for index, (key, label, icon) in enumerate(definitions)
    ]


def get_transaction_wizard(tx, user, requested_step=None):
    steps = get_transaction_steps(tx, user)
    default = next(step for step in steps if step["current"])
    if tx.status == Status.DRAFT and steps[0]["key"] == "policy_setup":
        default = steps[0]
    if tx.status == Status.NEEDS_INFORMATION:
        default = next(step for step in steps if step["key"] == "intake")
    selected = default
    if requested_step:
        match = next((step for step in steps if step["key"] == requested_step), None)
        if match is None:
            raise Http404("This step is not part of this transaction workflow.")
        if match["accessible"]:
            selected = match
    for step in steps:
        step["active"] = step is selected
    index = steps.index(selected)
    return {
        "workflow_steps": steps,
        "active_step": selected,
        "previous_step": steps[index - 1] if index else None,
        "next_step": steps[index + 1] if index + 1 < len(steps) else None,
        "step_number": index + 1,
        "step_url": selected["url"],
        "step_redirected": bool(requested_step and selected["key"] != requested_step),
        "transaction_closed": tx.status in CLOSED_STATUSES,
    }
