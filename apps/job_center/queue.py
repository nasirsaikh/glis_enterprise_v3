from datetime import timedelta

from django.utils import timezone

from .models import QueuedJob


def enqueue(handler,parameters=None,*,delay_seconds=0,priority=5,max_attempts=3,retry_delay_seconds=60,):
    return QueuedJob.objects.create(handler=handler,
                                    parameters=parameters or {},
                                    priority=priority,
                                    run_after=(timezone.now() + timedelta(seconds=delay_seconds)),
                                    max_attempts=max_attempts,
                                    retry_delay_seconds=retry_delay_seconds,
                                    )