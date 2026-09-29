from django.contrib.auth import get_user_model

from apps.job_center.registry import register_job
from apps.tpa.services.mailbox import poll_inbound_mailbox


@register_job("tpa.poll_inbound_mailbox")
def poll_tpa_inbound_mailbox(actor_id=None, limit=None, process_ai=None):
    User = get_user_model()
    actor = None
    if actor_id:
        actor = User.objects.filter(pk=actor_id, is_active=True).first()
    if actor is None:
        actor = (
            User.objects.filter(is_superuser=True, is_active=True)
            .order_by("pk")
            .first()
        )
    if actor is None:
        raise RuntimeError(
            "TPA mailbox polling needs an active actor. Configure actor_id "
            "or create an active superuser."
        )
    return poll_inbound_mailbox(
        actor=actor,
        limit=(max(int(limit), 1) if limit not in (None, "") else None),
        process_ai=process_ai,
    )
