from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.tickets.models import Ticket
from services.ticket_workflow import notify_users

from .models import Task


@receiver(pre_save, sender=Ticket)
def remember_task_ticket_status(sender, instance, **kwargs):
    if not instance.pk:
        instance._task_previous_status = None
        return
    instance._task_previous_status = (
        Ticket.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    )


@receiver(post_save, sender=Ticket)
def notify_task_watchers_on_status_change(sender, instance, created, **kwargs):
    if created:
        return
    previous = getattr(instance, "_task_previous_status", None)
    if not previous or previous == instance.status:
        return
    try:
        task = instance.task_item
    except Task.DoesNotExist:
        return
    if task.is_deleted:
        return
    users = {task.owner_id: task.owner}
    users.update({user.pk: user for user in task.tagged_users.all()})
    notify_users(
        list(users.values()),
        ticket=instance,
        kind="update",
        title=f"Task status updated: {instance.reference}",
        body=f"{task.title}: {previous.replace('_', ' ').title()} → {instance.get_status_display()}",
        send_email_message=task.category.send_update_email,
    )
