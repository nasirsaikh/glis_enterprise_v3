from django.db.models import Q
from services.tenancy import organization_ids, scope_policies

from ..models import (
    MemberTransaction,
    InboundEmail,
    Policy,
    PolicyAccess,
    TransactionQuery,
    TransactionQueryMessage,
)


TPA_ENTRY_PERMISSIONS = (
    "tpa.view_tpa_dashboard",
    "tpa.configure_tpa",
    "tpa.create_enrollment",
    "tpa.create_endorsement",
    "tpa.approve_endorsement",
    "tpa.process_endorsement",
)


def can_access_tpa(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or any(user.has_perm(code) for code in TPA_ENTRY_PERMISSIONS):
        return True
    if PolicyAccess.objects.filter(user=user, active=True, can_view=True).exists():
        return True
    return visible_transactions(user).exists()


def can_create_policy_enrollment(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm("tpa.configure_tpa"):
        return True
    if user.has_perm("tpa.create_enrollment"):
        return True
    return PolicyAccess.objects.filter(
        user=user,
        active=True,
        can_create_enrollment=True,
    ).exists()


def can_create_endorsement(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm("tpa.configure_tpa"):
        return True
    if user.has_perm("tpa.create_endorsement"):
        return True
    return PolicyAccess.objects.filter(
        user=user,
        active=True,
        can_create_endorsement=True,
    ).exists()


def can_create_tpa_transaction(user):
    return can_create_policy_enrollment(user) or can_create_endorsement(user)


def can_create_for_policy(user, policy, transaction_type):
    if not user or not user.is_authenticated or not visible_policies(user).filter(pk=policy.pk).exists():
        return False
    if user.is_superuser or user.has_perm("tpa.configure_tpa"):
        return True
    enrollment = transaction_type == MemberTransaction.Type.NEW_POLICY_ENROLLMENT
    if user.has_perm("tpa.create_enrollment" if enrollment else "tpa.create_endorsement"):
        return True
    return policy.access_entries.filter(user=user, active=True,
        **{"can_create_enrollment" if enrollment else "can_create_endorsement":True}).exists()


def can_edit_tpa_intake(user, tx):
    from apps.tickets.models import Ticket
    if tx.ticket_id and Ticket.objects.filter(pk=tx.ticket_id, status=Ticket.Status.CLOSED).exists():
        return False
    if not visible_transactions(user).filter(pk=tx.pk).exists():
        return False
    return can_create_for_policy(user,tx.policy,tx.transaction_type)


def can_approve_tpa_transaction(user, tx):
    if not user or not user.is_authenticated:
        return False
    if not visible_transactions(user).filter(pk=tx.pk).exists():
        return False
    from services.access import organization_allows
    if user.is_superuser or user.has_perm("tpa.configure_tpa") or (user.has_perm("tpa.approve_endorsement") and organization_allows(user,tx.ticket,"can_approve")):
        return True
    return PolicyAccess.objects.filter(
        user=user, policy=tx.policy, active=True, can_approve=True
    ).exists()


def can_process_tpa_transaction(user, tx):
    if not user or not user.is_authenticated:
        return False
    if not visible_transactions(user).filter(pk=tx.pk).exists():
        return False
    from services.access import organization_allows
    if user.is_superuser or user.has_perm("tpa.configure_tpa") or (user.has_perm("tpa.process_endorsement") and organization_allows(user,tx.ticket,"can_edit")):
        return True
    return PolicyAccess.objects.filter(
        user=user, policy=tx.policy, active=True, can_process=True
    ).exists()


def visible_policies(user):
    qs = scope_policies(Policy.objects.select_related("organization", "insurance_company"), user)
    if not user.is_authenticated:
        return qs.none()
    if user.is_superuser or any(user.has_perm(code) for code in (*TPA_ENTRY_PERMISSIONS, "tpa.view_policy")):
        return qs
    return qs.filter(
        access_entries__user=user,
        access_entries__active=True,
        access_entries__can_view=True,
    ).distinct()


def visible_transactions(user):
    from services.access import TicketAccessPolicy
    qs = MemberTransaction.objects.select_related('policy','organization','insurer','ticket')
    if not user or not user.is_authenticated:
        return qs.none()
    if user.is_superuser:
        return qs
    return qs.filter(Q(ticket_id__in=TicketAccessPolicy.visible_queryset(user).values('pk')) | Q(policy_id__in=visible_policies(user).values('pk'))).distinct()


def _is_internal_tpa_user(user, tx):
    return (
        user.is_superuser
        or user.has_perm("tpa.configure_tpa")
        or can_approve_tpa_transaction(user, tx)
        or can_process_tpa_transaction(user, tx)
    )


def can_view_transaction_query(user, query):
    if not user or not user.is_authenticated:
        return False
    tx = query.transaction
    if _is_internal_tpa_user(user, tx):
        return True
    if query.audience == TransactionQuery.Audience.INSURER_TPA_INTERNAL:
        return False
    if query.audience == TransactionQuery.Audience.SELECTED_PARTICIPANTS:
        return query.selected_participants.filter(pk=user.pk).exists()
    return (
        user.pk == tx.requester_id
        or query.selected_participants.filter(pk=user.pk).exists()
    )


def can_view_query_message(user, message):
    if not user or not user.is_authenticated:
        return False
    query = message.query
    tx = query.transaction
    if _is_internal_tpa_user(user, tx):
        return True

    # A deliberately shared internal message may be shown to the requester
    # without exposing the internal parent thread.  Query-level visibility is
    # therefore checked after this explicit exception.
    if message.audience == TransactionQuery.Audience.INSURER_TPA_INTERNAL:
        if not message.shared_with_client_at:
            return False
        return (
            user.pk == tx.requester_id
            or query.selected_participants.filter(pk=user.pk).exists()
        )

    if not can_view_transaction_query(user, query):
        return False
    if message.audience == TransactionQuery.Audience.SELECTED_PARTICIPANTS:
        return query.selected_participants.filter(pk=user.pk).exists()
    return True


def can_view_query_attachment(user, message):
    """Protect chat files independently from message-body sharing.

    Sharing an internal message exposes only the selected message body.  Its
    internal attachments remain insurer/TPA-only unless a future explicit
    attachment-sharing workflow is added.
    """
    tx = message.query.transaction
    if _is_internal_tpa_user(user, tx):
        return True
    if message.audience == TransactionQuery.Audience.INSURER_TPA_INTERNAL:
        return False
    return can_view_query_message(user, message)


def visible_shared_internal_messages(user, tx):
    if not user or not user.is_authenticated or _is_internal_tpa_user(user, tx):
        return TransactionQueryMessage.objects.none()

    qs = (
        TransactionQueryMessage.objects.select_related(
            "sender__profile",
            "ticket_comment",
            "query",
            "query__transaction",
        )
        .filter(
            query__transaction=tx,
            audience=TransactionQuery.Audience.INSURER_TPA_INTERNAL,
            shared_with_client_at__isnull=False,
        )
    )
    if user.pk == tx.requester_id:
        return qs.order_by("created_at", "pk")
    return qs.filter(query__selected_participants=user).distinct().order_by(
        "created_at", "pk"
    )


def visible_transaction_queries(user, tx):
    qs = tx.queries.select_related(
        "ticket", "raised_by", "resolved_by", "transaction"
    ).prefetch_related(
        "selected_participants",
        "messages__sender__profile",
        "messages__ticket_comment",
        "messages__ticket_comment__attachments",
    )
    if _is_internal_tpa_user(user, tx):
        return qs
    return qs.filter(
        Q(audience=TransactionQuery.Audience.CLIENT_VISIBLE)
        | Q(selected_participants=user)
    ).distinct()


def visible_inbound_emails(user):
    qs = InboundEmail.objects.select_related("transaction", "transaction__policy", "created_by")
    if not user or not user.is_authenticated:
        return qs.none()
    if user.is_superuser:
        return qs
    policies = visible_policies(user)
    return qs.filter(
        Q(created_by=user, provider="manual")
        | Q(transaction_id__in=visible_transactions(user).values("pk"))
        | Q(ai_extracted_payload__policy_number__in=policies.values("policy_number"))
        | Q(processing_hints__policy_id__in=policies.values("pk"))
    ).distinct()
