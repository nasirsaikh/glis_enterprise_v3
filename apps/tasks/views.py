from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.tickets.models import SLAPolicy, Ticket, TicketEvent
from services.ticket_workflow import notify_users

from .forms import TaskForm
from .models import Task
from .services import create_ticket_for_task


def _visible_tasks(user):
    queryset = (
        Task.objects.filter(is_deleted=False)
        .select_related("ticket", "project", "product", "category", "owner", "recurring_task")
        .prefetch_related("tagged_users")
    )
    if user.is_staff or user.is_superuser or user.has_perm("tasks.manage_tasks"):
        return queryset
    return queryset.filter(Q(owner=user) | Q(tagged_users=user) | Q(created_by=user)).distinct()


def _can_manage(user, task=None):
    if user.is_staff or user.is_superuser or user.has_perm("tasks.manage_tasks"):
        return True
    if task is None:
        return True
    return task.owner_id == user.pk or task.created_by_id == user.pk


def _sync_ticket_from_task(task, ticket, status):
    hierarchy_changed = (
        ticket.category_id != task.category_id
        or ticket.priority != task.priority
    )
    ticket.subject = task.title
    ticket.description = task.description or f"Task due {task.due_date:%d-%b-%Y}"
    ticket.project = task.project
    ticket.product = task.product
    ticket.category = task.category
    ticket.priority = task.priority
    ticket.assignee = task.owner

    if hierarchy_changed:
        sla = (
            SLAPolicy.objects.filter(
                category=task.category,
                priority=task.priority,
                is_active=True,
            )
            .order_by("pk")
            .first()
        )
        ticket.sla_policy = sla
        base_time = ticket.created_at or timezone.now()
        ticket.first_response_due_at = (
            base_time + timedelta(minutes=sla.first_response_minutes)
            if sla
            else None
        )
        ticket.resolution_due_at = (
            base_time + timedelta(minutes=sla.resolution_minutes)
            if sla
            else None
        )

    if status == Ticket.Status.RESOLVED:
        if ticket.status != Ticket.Status.RESOLVED or not ticket.resolved_at:
            ticket.resolved_at = timezone.now()
        ticket.closed_at = None
    elif status == Ticket.Status.CLOSED:
        if ticket.status != Ticket.Status.CLOSED or not ticket.closed_at:
            ticket.closed_at = timezone.now()
    else:
        ticket.resolved_at = None
        ticket.closed_at = None

    ticket.status = status
    ticket.save()
    ticket.assignees.set([task.owner])

    default_groups = list(task.category.default_groups.filter(is_active=True))
    if task.category.default_group and task.category.default_group not in default_groups:
        default_groups.append(task.category.default_group)
    ticket.groups.set(default_groups)


def _apply_filters(request, queryset):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    source = request.GET.get("source", "").strip()
    if q:
        queryset = queryset.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(ticket__reference__icontains=q)
            | Q(owner__first_name__icontains=q)
            | Q(owner__last_name__icontains=q)
            | Q(owner__email__icontains=q)
        )
    if status:
        queryset = queryset.filter(ticket__status=status)
    if source == "recurring":
        queryset = queryset.filter(recurring_task__isnull=False)
    elif source == "manual":
        queryset = queryset.filter(recurring_task__isnull=True)
    return queryset


def _task_context(request):
    queryset = _apply_filters(request, _visible_tasks(request.user)).order_by("due_date", "title")
    return {
        "tasks": queryset[:250],
        "status_choices": Ticket.Status.choices,
        "current_status": request.GET.get("status", ""),
        "current_source": request.GET.get("source", ""),
        "query": request.GET.get("q", ""),
        "today": timezone.localdate(),
    }


@login_required
def task_list(request):
    template = "tasks/partials/table.html" if request.headers.get("HX-Request") else "tasks/list.html"
    return render(request, template, _task_context(request))


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def task_create(request):
    if not _can_manage(request.user):
        return HttpResponse("Task creation permission is required.", status=403)
    form = TaskForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        task = form.save(commit=False)
        task.occurrence_date = task.due_date
        task.created_by = request.user
        task.updated_by = request.user
        task.save()
        form.save_m2m()
        ticket = create_ticket_for_task(task, actor=request.user)
        _sync_ticket_from_task(task, ticket, form.cleaned_data["status"])
        messages.success(request, f"Task created and linked to {task.ticket.reference}.")
        return render(request, "tasks/partials/mutation_success.html", _task_context(request))
    return render(request, "tasks/partials/form.html", {"form": form, "task": None})


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def task_edit(request, pk):
    task = get_object_or_404(_visible_tasks(request.user), pk=pk)
    if not _can_manage(request.user, task):
        return HttpResponse("Only the task owner or a task manager can edit this task.", status=403)
    form = TaskForm(request.POST or None, instance=task, user=request.user)
    if request.method == "POST" and form.is_valid():
        previous_owner_id = task.owner_id
        updated = form.save(commit=False)
        updated.updated_by = request.user
        updated.save()
        form.save_m2m()
        ticket = create_ticket_for_task(updated, actor=request.user)

        _sync_ticket_from_task(updated, ticket, form.cleaned_data["status"])

        TicketEvent.objects.create(
            ticket=ticket,
            actor=request.user,
            event_type="task_updated",
            summary="Task details updated",
            details={"task_id": updated.pk, "due_date": updated.due_date.isoformat()},
        )
        if previous_owner_id != updated.owner_id:
            notify_users(
                [updated.owner],
                ticket=ticket,
                kind="assignment",
                title=f"Task assigned: {ticket.reference}",
                body=f"{updated.title} · due {updated.due_date:%d-%b-%Y}",
                send_email_message=updated.category.send_update_email,
            )
        messages.success(request, "Task changes were saved.")
        return render(request, "tasks/partials/mutation_success.html", _task_context(request))
    return render(request, "tasks/partials/form.html", {"form": form, "task": task})


@login_required
@require_POST
@transaction.atomic
def task_delete(request, pk):
    task = get_object_or_404(_visible_tasks(request.user), pk=pk)
    if not _can_manage(request.user, task):
        return HttpResponse("Only the task owner or a task manager can delete this task.", status=403)
    task.is_deleted = True
    task.updated_by = request.user
    task.save(update_fields=["is_deleted", "updated_by", "updated_at"])
    if task.ticket_id:
        ticket = task.ticket
        ticket.status = Ticket.Status.CLOSED
        if not ticket.closed_at:
            ticket.closed_at = timezone.now()
        ticket.save(update_fields=["status", "closed_at", "updated_at"])
        TicketEvent.objects.create(
            ticket=ticket,
            actor=request.user,
            event_type="task_deleted",
            summary="Task removed from the active task list",
            details={"task_id": task.pk},
        )
    messages.success(request, "Task was removed from the active task list.")
    return render(request, "tasks/partials/table.html", _task_context(request))
