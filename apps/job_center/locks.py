import os
import socket
import threading
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import SchedulerLock


LOCK_NAME = "job_center_scheduler"
OWNER = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def lock_ttl_seconds() -> int:
    return int(getattr(settings, "JOB_CENTER_LOCK_TTL_SECONDS", 90))


def heartbeat_seconds() -> int:
    return int(getattr(settings, "JOB_CENTER_HEARTBEAT_SECONDS", 30))


def try_acquire_lock() -> bool:
    now = timezone.now()
    expires = now + timedelta(seconds=lock_ttl_seconds())

    with transaction.atomic():
        lock, _ = SchedulerLock.objects.select_for_update().get_or_create(
            name=LOCK_NAME,
            defaults={
                "owner": "",
                "heartbeat_at": None,
                "expires_at": None,
            },
        )

        can_take = (
            not lock.owner
            or lock.owner == OWNER
            or lock.expires_at is None
            or lock.expires_at <= now
        )

        if not can_take:
            return False

        lock.owner = OWNER
        lock.heartbeat_at = now
        lock.expires_at = expires
        lock.save(update_fields=["owner", "heartbeat_at", "expires_at", "updated_at"])
        return True


def refresh_lock() -> bool:
    now = timezone.now()
    expires = now + timedelta(seconds=lock_ttl_seconds())

    updated = SchedulerLock.objects.filter(
        name=LOCK_NAME,
        owner=OWNER,
    ).update(
        heartbeat_at=now,
        expires_at=expires,
    )
    return bool(updated)


def release_lock():
    SchedulerLock.objects.filter(
        name=LOCK_NAME,
        owner=OWNER,
    ).update(
        owner="",
        heartbeat_at=None,
        expires_at=None,
    )


def current_owner():
    lock = SchedulerLock.objects.filter(name=LOCK_NAME).first()
    return lock.owner if lock else ""
