from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TimeStampedModel
from apps.tickets.models import Category, Product, Project, Ticket


class RecurringTask(TimeStampedModel):
    class Frequency(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        FORTNIGHTLY = "fortnightly", "Fortnightly"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        HALF_YEARLY = "half_yearly", "Half yearly"
        YEARLY = "yearly", "Yearly"
        ONE_TIME = "one_time", "One time"

    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    project = models.ForeignKey(Project, related_name="recurring_tasks", on_delete=models.PROTECT)
    product = models.ForeignKey(Product, related_name="recurring_tasks", on_delete=models.PROTECT)
    category = models.ForeignKey(Category, related_name="recurring_tasks", on_delete=models.PROTECT)
    priority = models.CharField(max_length=15, choices=Ticket.Priority.choices, default=Ticket.Priority.MEDIUM)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="owned_recurring_tasks", on_delete=models.PROTECT)
    tagged_users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="tagged_recurring_tasks", blank=True)
    first_due_date = models.DateField(help_text="The first due date in the recurrence pattern.")
    recurrence = models.CharField(max_length=20, choices=Frequency.choices, default=Frequency.MONTHLY)
    create_days_before = models.PositiveSmallIntegerField(
        default=0,
        help_text="Create each task and its ticket this many calendar days before the due date.",
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="created_recurring_tasks", on_delete=models.SET_NULL)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="updated_recurring_tasks", on_delete=models.SET_NULL)

    class Meta:
        ordering = ("title", "first_due_date")
        permissions = [("manage_recurring_tasks", "Can manage recurring tasks")]

    def clean(self):
        errors = {}
        if self.product_id and self.project_id and self.product.project_id != self.project_id:
            errors["product"] = "The selected product does not belong to the selected project."
        if self.category_id and self.product_id and self.category.product_id != self.product_id:
            errors["category"] = "The selected category does not belong to the selected product."
        if self.create_days_before > 3660:
            errors["create_days_before"] = "Create-days-before cannot exceed 3660 days."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.title


class Task(TimeStampedModel):
    recurring_task = models.ForeignKey(
        RecurringTask,
        null=True,
        blank=True,
        related_name="generated_tasks",
        on_delete=models.PROTECT,
    )
    occurrence_date = models.DateField(help_text="Scheduled recurrence date used for duplicate prevention.")
    due_date = models.DateField(db_index=True)
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    project = models.ForeignKey(Project, related_name="tasks", on_delete=models.PROTECT)
    product = models.ForeignKey(Product, related_name="tasks", on_delete=models.PROTECT)
    category = models.ForeignKey(Category, related_name="tasks", on_delete=models.PROTECT)
    priority = models.CharField(max_length=15, choices=Ticket.Priority.choices, default=Ticket.Priority.MEDIUM)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="owned_tasks", on_delete=models.PROTECT)
    tagged_users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="tagged_tasks", blank=True)
    ticket = models.OneToOneField(
        Ticket,
        null=True,
        blank=True,
        related_name="task_item",
        on_delete=models.SET_NULL,
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="created_tasks", on_delete=models.SET_NULL)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, related_name="updated_tasks", on_delete=models.SET_NULL)
    is_deleted = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ("due_date", "title")
        permissions = [("manage_tasks", "Can manage tasks")]
        constraints = [
            models.UniqueConstraint(
                fields=("recurring_task", "occurrence_date"),
                condition=models.Q(recurring_task__isnull=False),
                name="unique_recurring_task_occurrence",
            )
        ]

    def clean(self):
        errors = {}
        if self.product_id and self.project_id and self.product.project_id != self.project_id:
            errors["product"] = "The selected product does not belong to the selected project."
        if self.category_id and self.product_id and self.category.product_id != self.product_id:
            errors["category"] = "The selected category does not belong to the selected product."
        if errors:
            raise ValidationError(errors)

    @property
    def status(self):
        return self.ticket.status if self.ticket_id else Ticket.Status.NEW

    @property
    def status_display(self):
        return self.ticket.get_status_display() if self.ticket_id else "New"

    @property
    def is_recurring(self):
        return bool(self.recurring_task_id)

    def __str__(self):
        return f"{self.title} · {self.due_date:%d-%b-%Y}"
