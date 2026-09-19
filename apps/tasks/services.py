import calendar
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.tickets.models import SLAPolicy, Ticket, TicketEvent
from services.ticket_workflow import initialize_approval_workflow, notify_users

from .models import RecurringTask, Task


def _add_months(value: date, months: int) -> date:
    month_index = (value.month - 1) + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def next_occurrence(value: date, frequency: str):
    if frequency == RecurringTask.Frequency.DAILY:
        return value + timedelta(days=1)
    if frequency == RecurringTask.Frequency.WEEKLY:
        return value + timedelta(days=7)
    if frequency == RecurringTask.Frequency.FORTNIGHTLY:
        return value + timedelta(days=14)
    if frequency == RecurringTask.Frequency.MONTHLY:
        return _add_months(value, 1)
    if frequency == RecurringTask.Frequency.QUARTERLY:
        return _add_months(value, 3)
    if frequency == RecurringTask.Frequency.HALF_YEARLY:
        return _add_months(value, 6)
    if frequency == RecurringTask.Frequency.YEARLY:
        return _add_months(value, 12)
    return None


def _notification_users(task: Task):
    users = {task.owner_id: task.owner}
    users.update({user.pk: user for user in task.tagged_users.all()})
    return list(users.values())


@transaction.atomic
def create_ticket_for_task(task: Task, *, actor=None):
    if task.ticket_id:
        return task.ticket

    sla = (
        SLAPolicy.objects.filter(
            category=task.category,
            priority=task.priority,
            is_active=True,
        )
        .order_by("pk")
        .first()
    )
    now = timezone.now()
    ticket = Ticket.objects.create(
        subject=task.title,
        description=task.description or f"Task due {task.due_date:%d-%b-%Y}",
        requester=task.owner,
        assignee=task.owner,
        project=task.project,
        product=task.product,
        category=task.category,
        priority=task.priority,
        tags=["task", "recurring-task" if task.recurring_task_id else "manual-task"],
        sla_policy=sla,
        first_response_due_at=now + timedelta(minutes=sla.first_response_minutes) if sla else None,
        resolution_due_at=now + timedelta(minutes=sla.resolution_minutes) if sla else None,
    )

    ticket.assignees.add(task.owner)
    default_groups = list(task.category.default_groups.filter(is_active=True))
    if task.category.default_group and task.category.default_group not in default_groups:
        default_groups.append(task.category.default_group)
    if default_groups:
        ticket.groups.add(*default_groups)

    task.ticket = ticket
    task.save(update_fields=["ticket", "updated_at"])

    TicketEvent.objects.create(
        ticket=ticket,
        actor=actor,
        event_type="task_created",
        summary=f"Task created for {task.due_date:%d-%b-%Y}",
        details={
            "task_id": task.pk,
            "recurring_task_id": task.recurring_task_id,
            "due_date": task.due_date.isoformat(),
        },
    )
    initialize_approval_workflow(ticket)
    notify_users(
        _notification_users(task),
        ticket=ticket,
        kind="assignment",
        title=f"Task assigned: {ticket.reference}",
        body=f"{task.title} · due {task.due_date:%d-%b-%Y}",
        send_email_message=task.category.send_initial_email,
    )
    return ticket


@transaction.atomic
def create_manual_task(*, actor, **task_data):
    tagged_users = task_data.pop("tagged_users", [])
    due_date = task_data["due_date"]
    task = Task.objects.create(
        occurrence_date=due_date,
        created_by=actor,
        updated_by=actor,
        **task_data,
    )
    task.tagged_users.set(tagged_users)
    create_ticket_for_task(task, actor=actor)
    return task


def generate_due_tasks(*, as_of=None, max_per_template=500):
    today = as_of or timezone.localdate()
    created = 0
    processed = 0
    errors = []

    template_ids = list(RecurringTask.objects.filter(is_active=True).values_list("pk", flat=True))
    for template_id in template_ids:
        processed += 1
        try:
            with transaction.atomic():
                template = (
                    RecurringTask.objects.select_for_update()
                    .select_related("project", "product", "category", "owner")
                    .get(pk=template_id, is_active=True)
                )
                latest = (
                    template.generated_tasks.order_by("-occurrence_date")
                    .values_list("occurrence_date", flat=True)
                    .first()
                )
                candidate = template.first_due_date if latest is None else next_occurrence(latest, template.recurrence)
                iterations = 0

                while candidate and candidate - timedelta(days=template.create_days_before) <= today:
                    iterations += 1
                    if iterations > max_per_template:
                        raise RuntimeError(
                            f"Generation safety limit exceeded for recurring task {template.pk}."
                        )

                    try:
                        task, was_created = Task.objects.get_or_create(
                            recurring_task=template,
                            occurrence_date=candidate,
                            defaults={
                                "due_date": candidate,
                                "title": template.title,
                                "description": template.description,
                                "project": template.project,
                                "product": template.product,
                                "category": template.category,
                                "priority": template.priority,
                                "owner": template.owner,
                                "created_by": template.created_by or template.owner,
                                "updated_by": template.updated_by or template.owner,
                            },
                        )
                    except IntegrityError:
                        task = Task.objects.get(recurring_task=template, occurrence_date=candidate)
                        was_created = False

                    if was_created:
                        task.tagged_users.set(template.tagged_users.all())
                        create_ticket_for_task(task, actor=template.created_by)
                        created += 1

                    if template.recurrence == RecurringTask.Frequency.ONE_TIME:
                        break
                    candidate = next_occurrence(candidate, template.recurrence)
        except Exception as exc:
            errors.append({"recurring_task_id": template_id, "error": str(exc)})

    return {
        "success": not errors,
        "created": created,
        "templates_processed": processed,
        "as_of": today.isoformat(),
        "errors": errors,
    }
